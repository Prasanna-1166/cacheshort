"""Unit and integration tests for API key authentication and production security."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import (
    generate_api_key,
    hash_api_key,
    validate_api_key_format,
    API_KEY_PREFIX,
    API_KEY_HEADER_NAME,
)
from app.database.api_key_repository import (
    InMemoryAPIKeyRepository,
    get_api_key_repository,
)
from app.database.repository import InMemoryURLRepository, get_repository
from app.cache.lru_cache import LRUCache
from app.core.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter
from app.services.url_service import URLService, get_url_service, get_global_cache


@pytest.fixture
def auth_environment():
    """Setup in-memory repositories, LRU cache, and test API key."""
    key_repo = InMemoryAPIKeyRepository()
    url_repo = InMemoryURLRepository()
    cache = LRUCache(capacity=10)
    limiter = SlidingWindowRateLimiter(requests=100, window_seconds=60)

    # Generate a valid active test key
    raw_key, prefix, key_hash = generate_api_key()
    active_record = key_repo.create_api_key(name="test-active-key", key_prefix=prefix, key_hash=key_hash)

    # Generate a revoked test key
    revoked_raw_key, revoked_prefix, revoked_hash = generate_api_key()
    revoked_record = key_repo.create_api_key(name="test-revoked-key", key_prefix=revoked_prefix, key_hash=revoked_hash)
    key_repo.revoke_key(revoked_record.id)

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
        "url_repo": url_repo,
        "cache": cache,
        "raw_key": raw_key,
        "active_record": active_record,
        "revoked_raw_key": revoked_raw_key,
        "revoked_record": revoked_record,
    }

    app.dependency_overrides.clear()


@pytest.fixture
def client(auth_environment) -> TestClient:
    return TestClient(app)


def test_api_key_generation_format():
    """Verify generated API keys start with prefix and have sufficient entropy."""
    raw_key, prefix, key_hash = generate_api_key()

    assert raw_key.startswith(API_KEY_PREFIX)
    assert len(raw_key) > 30
    assert prefix == raw_key[:12]
    assert len(key_hash) == 64  # SHA-256 hex string
    assert validate_api_key_format(raw_key) is True


def test_api_key_randomness():
    """Verify consecutive generated keys are unique."""
    keys = {generate_api_key()[0] for _ in range(100)}
    assert len(keys) == 100


def test_api_key_hashing():
    """Verify deterministic SHA-256 hashing."""
    key = "cs_live_testkey123456789"
    hash1 = hash_api_key(key)
    hash2 = hash_api_key(key)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert hash_api_key("cs_live_differentkey123") != hash1


def test_api_key_validation_rejects_invalid_formats():
    """Verify validate_api_key_format rejects malformed strings."""
    assert validate_api_key_format(None) is False
    assert validate_api_key_format("") is False
    assert validate_api_key_format("invalid_prefix_123456789") is False
    assert validate_api_key_format("cs_live_short") is False
    assert validate_api_key_format("Bearer token123456789") is False


def test_protected_endpoints_reject_missing_api_key(client: TestClient):
    """Verify protected endpoints return 401 when X-API-Key header is missing."""
    # POST /api/urls
    r1 = client.post("/api/urls", json={"url": "https://example.com/test"})
    assert r1.status_code == 401
    assert r1.json()["detail"] == "Invalid or missing API key"

    # GET /api/urls/{code}
    r2 = client.get("/api/urls/somecode")
    assert r2.status_code == 401
    assert r2.json()["detail"] == "Invalid or missing API key"

    # GET /api/urls/{code}/stats
    r3 = client.get("/api/urls/somecode/stats")
    assert r3.status_code == 401
    assert r3.json()["detail"] == "Invalid or missing API key"

    # GET /api/cache/stats
    r4 = client.get("/api/cache/stats")
    assert r4.status_code == 401
    assert r4.json()["detail"] == "Invalid or missing API key"


def test_protected_endpoints_reject_invalid_api_key(client: TestClient):
    """Verify protected endpoints return 401 when an unknown or invalid key is provided."""
    headers = {API_KEY_HEADER_NAME: "cs_live_completely_fake_and_unknown_key"}
    resp = client.post("/api/urls", json={"url": "https://example.com/test"}, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing API key"


def test_protected_endpoints_reject_revoked_api_key(client: TestClient, auth_environment):
    """Verify revoked API keys return 401 with uniform error message."""
    headers = {API_KEY_HEADER_NAME: auth_environment["revoked_raw_key"]}
    resp = client.post("/api/urls", json={"url": "https://example.com/test"}, headers=headers)
    assert resp.status_code == 401
    # Error message must be identical to invalid key to avoid leaking key existence
    assert resp.json()["detail"] == "Invalid or missing API key"


def test_protected_endpoints_succeed_with_valid_api_key(client: TestClient, auth_environment):
    """Verify protected endpoints succeed when a valid active API key is provided."""
    headers = {API_KEY_HEADER_NAME: auth_environment["raw_key"]}

    # POST /api/urls
    target = "https://fastapi.tiangolo.com/"
    create_resp = client.post("/api/urls", json={"url": target}, headers=headers)
    assert create_resp.status_code == 201
    short_code = create_resp.json()["short_code"]

    # GET /api/urls/{short_code}
    info_resp = client.get(f"/api/urls/{short_code}", headers=headers)
    assert info_resp.status_code == 200
    assert info_resp.json()["short_code"] == short_code

    # GET /api/urls/{short_code}/stats
    stats_resp = client.get(f"/api/urls/{short_code}/stats", headers=headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json()["short_code"] == short_code

    # GET /api/cache/stats
    cache_resp = client.get("/api/cache/stats", headers=headers)
    assert cache_resp.status_code == 200
    assert "hits" in cache_resp.json()


def test_api_key_last_used_at_updates_on_verification(client: TestClient, auth_environment):
    """Verify last_used_at is updated in the repository when key is verified."""
    key_repo = auth_environment["key_repo"]
    record = auth_environment["active_record"]
    assert record.last_used_at is None

    headers = {API_KEY_HEADER_NAME: auth_environment["raw_key"]}
    resp = client.get("/api/cache/stats", headers=headers)
    assert resp.status_code == 200

    updated_record = key_repo.get_by_hash(record.key_hash)
    assert updated_record is not None
    assert updated_record.last_used_at is not None


def test_public_endpoints_remain_unauthenticated(client: TestClient, auth_environment):
    """Verify /health and /{short_code} do not require API keys."""
    # 1. Health check
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # 2. Create short URL (using auth)
    headers = {API_KEY_HEADER_NAME: auth_environment["raw_key"]}
    create_resp = client.post("/api/urls", json={"url": "https://example.com/public-redirect"}, headers=headers)
    assert create_resp.status_code == 201
    short_code = create_resp.json()["short_code"]

    # 3. Public redirect (WITHOUT headers)
    redirect_resp = client.get(f"/{short_code}", follow_redirects=False)
    assert redirect_resp.status_code == 307
    assert redirect_resp.headers["location"] == "https://example.com/public-redirect"


def test_bearer_token_not_accepted(client: TestClient, auth_environment):
    """Verify Authorization: Bearer is NOT accepted in this phase."""
    bearer_headers = {"Authorization": f"Bearer {auth_environment['raw_key']}"}
    resp = client.post("/api/urls", json={"url": "https://example.com/bearer"}, headers=bearer_headers)
    assert resp.status_code == 401


def test_in_memory_api_key_repo_operations():
    """Verify InMemoryAPIKeyRepository handles CRUD, revocation, and collisions."""
    repo = InMemoryAPIKeyRepository()
    record = repo.create_api_key("admin", "cs_live_1234", "hash1234567890123456789012345678901234567890123456789012345678901234")
    assert record.id == 1
    assert record.is_active is True
    assert record.revoked_at is None

    # Duplicate hash raises ValueError
    with pytest.raises(ValueError, match="already exists"):
        repo.create_api_key("admin2", "cs_live_1234", "hash1234567890123456789012345678901234567890123456789012345678901234")

    # Lookup
    found = repo.get_by_hash("hash1234567890123456789012345678901234567890123456789012345678901234")
    assert found is not None
    assert found.id == 1

    # Revoke
    assert repo.revoke_key(1) is True
    assert repo.revoke_key(1) is False  # Already revoked
    assert record.is_active is False
    assert record.revoked_at is not None

    # Clear
    repo.clear()
    assert repo.get_by_hash("hash1234567890123456789012345678901234567890123456789012345678901234") is None

