"""Unit and API integration tests for API Key lifecycle management (create, list, revoke)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import generate_api_key, API_KEY_HEADER_NAME
from app.database.api_key_repository import InMemoryAPIKeyRepository, get_api_key_repository
from app.database.repository import InMemoryURLRepository, get_repository
from app.cache.lru_cache import LRUCache
from app.core.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter
from app.services.url_service import URLService, get_url_service, get_global_cache


@pytest.fixture
def key_env():
    """Setup in-memory key repo and authenticated test client."""
    key_repo = InMemoryAPIKeyRepository()
    url_repo = InMemoryURLRepository()
    cache = LRUCache(capacity=10)
    limiter = SlidingWindowRateLimiter(requests=100, window_seconds=60)

    # Master/Admin active key
    admin_raw_key, prefix, key_hash = generate_api_key()
    admin_record = key_repo.create_api_key(name="admin-root-key", key_prefix=prefix, key_hash=key_hash)

    def override_get_api_key_repo():
        return key_repo

    def override_get_repository():
        return url_repo

    def override_get_global_cache():
        return cache

    def override_get_rate_limiter():
        return limiter

    def override_get_url_service():
        return URLService(repository=url_repo, cache=cache, base_url="http://testserver")

    app.dependency_overrides[get_api_key_repository] = override_get_api_key_repo
    app.dependency_overrides[get_repository] = override_get_repository
    app.dependency_overrides[get_global_cache] = override_get_global_cache
    app.dependency_overrides[get_rate_limiter] = override_get_rate_limiter
    app.dependency_overrides[get_url_service] = override_get_url_service

    yield {
        "key_repo": key_repo,
        "admin_raw_key": admin_raw_key,
        "admin_record": admin_record,
    }

    app.dependency_overrides.clear()


@pytest.fixture
def client(key_env) -> TestClient:
    c = TestClient(app)
    c.headers.update({API_KEY_HEADER_NAME: key_env["admin_raw_key"]})
    return c


@pytest.fixture
def unauth_client(key_env) -> TestClient:
    return TestClient(app)


def test_create_api_key_success(client: TestClient):
    """Verify POST /api/keys generates a new key and returns raw_key once."""
    payload = {"name": "ci-cd-runner"}
    response = client.post("/api/keys", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "ci-cd-runner"
    assert "id" in data
    assert "key_prefix" in data
    assert "raw_key" in data
    assert data["raw_key"].startswith("cs_live_")
    assert data["raw_key"][:12] == data["key_prefix"]
    assert "key_hash" not in data


def test_newly_created_key_can_authenticate(client: TestClient, unauth_client: TestClient):
    """Verify newly created key can immediately authenticate to protected endpoints."""
    create_resp = client.post("/api/keys", json={"name": "new-service-key"})
    assert create_resp.status_code == 201
    new_raw_key = create_resp.json()["raw_key"]

    # Use new key to shorten a URL
    headers = {API_KEY_HEADER_NAME: new_raw_key}
    url_resp = unauth_client.post("/api/urls", json={"url": "https://fastapi.tiangolo.com/"}, headers=headers)
    assert url_resp.status_code == 201
    assert "short_code" in url_resp.json()


def test_list_api_keys_metadata_only(client: TestClient):
    """Verify GET /api/keys returns metadata without leaking key_hash or raw plaintext."""
    client.post("/api/keys", json={"name": "service-alpha"})
    client.post("/api/keys", json={"name": "service-beta"})

    response = client.get("/api/keys")
    assert response.status_code == 200
    keys = response.json()

    assert len(keys) >= 3  # Root admin + alpha + beta
    for k in keys:
        assert "id" in k
        assert "name" in k
        assert "key_prefix" in k
        assert "is_active" in k
        assert "created_at" in k
        assert "key_hash" not in k
        assert "raw_key" not in k


def test_revoke_api_key_lifecycle(client: TestClient, unauth_client: TestClient):
    """Verify DELETE /api/keys/{id} deactivates key and prevents further authentication."""
    # 1. Create key
    create_resp = client.post("/api/keys", json={"name": "temporary-worker"})
    assert create_resp.status_code == 201
    created = create_resp.json()
    key_id = created["id"]
    temp_raw_key = created["raw_key"]

    # 2. Authenticate successfully with temp key
    headers = {API_KEY_HEADER_NAME: temp_raw_key}
    assert unauth_client.get("/api/cache/stats", headers=headers).status_code == 200

    # 3. Revoke key
    del_resp = client.delete(f"/api/keys/{key_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["revoked"] is True

    # 4. Authentication must now fail with 401
    fail_resp = unauth_client.get("/api/cache/stats", headers=headers)
    assert fail_resp.status_code == 401

    # 5. Revoking again returns idempotent revoked=False status
    re_del_resp = client.delete(f"/api/keys/{key_id}")
    assert re_del_resp.status_code == 200
    assert re_del_resp.json()["revoked"] is False


def test_revoke_nonexistent_key_returns_404(client: TestClient):
    """Verify DELETE /api/keys/{id} returns 404 for unknown key IDs."""
    response = client.delete("/api/keys/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "API key not found"


def test_api_keys_routes_require_authentication(unauth_client: TestClient):
    """Verify all /api/keys endpoints reject unauthenticated requests with 401."""
    assert unauth_client.post("/api/keys", json={"name": "test"}).status_code == 401
    assert unauth_client.get("/api/keys").status_code == 401
    assert unauth_client.delete("/api/keys/1").status_code == 401


def test_create_api_key_validates_name(client: TestClient):
    """Verify invalid names (empty/spaces/too long) are rejected with 422."""
    assert client.post("/api/keys", json={"name": ""}).status_code == 422
    assert client.post("/api/keys", json={"name": "   "}).status_code == 422
    assert client.post("/api/keys", json={"name": "x" * 65}).status_code == 422
