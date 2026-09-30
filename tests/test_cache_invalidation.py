"""Unit and API integration tests for administrative cache eviction and flush controls."""

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
def cache_env():
    """Setup test cache, repository, and auth credentials."""
    key_repo = InMemoryAPIKeyRepository()
    url_repo = InMemoryURLRepository()
    cache = LRUCache(capacity=10)
    limiter = SlidingWindowRateLimiter(requests=100, window_seconds=60)

    raw_key, prefix, key_hash = generate_api_key()
    key_repo.create_api_key(name="cache-admin-key", key_prefix=prefix, key_hash=key_hash)

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
    }

    app.dependency_overrides.clear()


@pytest.fixture
def client(cache_env) -> TestClient:
    c = TestClient(app)
    c.headers.update({API_KEY_HEADER_NAME: cache_env["raw_key"]})
    return c


@pytest.fixture
def unauth_client(cache_env) -> TestClient:
    return TestClient(app)


def test_evict_existing_cache_entry(client: TestClient, cache_env):
    """Verify DELETE /api/cache/entries/{short_code} removes key from LRU memory."""
    cache: LRUCache = cache_env["cache"]
    cache.put("alphaCode", "https://example.com/alpha")
    assert cache.size() == 1
    assert cache.get("alphaCode") == "https://example.com/alpha"

    response = client.delete("/api/cache/entries/alphaCode")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == "alphaCode"
    assert data["evicted"] is True
    assert cache.size() == 0

    # Subsequent lookup is a miss
    assert cache.get("alphaCode") is None


def test_evict_nonexistent_cache_entry(client: TestClient, cache_env):
    """Verify evicting unknown short code returns 200 with evicted=False."""
    response = client.delete("/api/cache/entries/nonexistentCode")
    assert response.status_code == 200
    data = response.json()
    assert data["short_code"] == "nonexistentCode"
    assert data["evicted"] is False


def test_clear_entire_cache(client: TestClient, cache_env):
    """Verify POST /api/cache/clear empties cache while preserving historical metrics."""
    cache: LRUCache = cache_env["cache"]
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.put("k3", "v3")
    cache.get("k1")  # generate 1 hit
    cache.get("missing")  # generate 1 miss

    stats_before = cache.stats()
    assert stats_before["current_size"] == 3
    assert stats_before["hits"] == 1
    assert stats_before["misses"] == 1

    response = client.post("/api/cache/clear")
    assert response.status_code == 200
    data = response.json()
    assert data["cleared_entries"] == 3

    # Size is zero
    assert cache.size() == 0

    # Historical metrics are preserved
    stats_after = cache.stats()
    assert stats_after["current_size"] == 0
    assert stats_after["hits"] == 1
    assert stats_after["misses"] == 1


def test_redirect_resolves_via_db_after_cache_eviction(client: TestClient, cache_env, unauth_client: TestClient):
    """Verify public redirect continues working by falling back to DB when cached entry is evicted."""
    target = "https://docs.python.org/3/"
    create_resp = client.post("/api/urls", json={"url": target})
    assert create_resp.status_code == 201
    code = create_resp.json()["short_code"]

    cache: LRUCache = cache_env["cache"]
    assert code in cache

    # Evict code from LRU cache
    del_resp = client.delete(f"/api/cache/entries/{code}")
    assert del_resp.status_code == 200
    assert del_resp.json()["evicted"] is True
    assert code not in cache

    # Public redirect still succeeds (cache miss -> database lookup -> re-populates cache)
    redir_resp = unauth_client.get(f"/{code}", follow_redirects=False)
    assert redir_resp.status_code == 307
    assert redir_resp.headers["location"] == target
    assert code in cache


def test_cache_admin_endpoints_require_authentication(unauth_client: TestClient):
    """Verify cache administration endpoints reject unauthenticated calls with 401."""
    assert unauth_client.delete("/api/cache/entries/test").status_code == 401
    assert unauth_client.post("/api/cache/clear").status_code == 401
