"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.repository import InMemoryURLRepository, get_repository
from app.cache.lru_cache import LRUCache
from app.core.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter
from app.services.url_service import get_global_cache, URLService, get_url_service


@pytest.fixture(autouse=True)
def clean_environment():
    """Ensure clean repository, cache, and rate limiter state for each API test."""
    test_repo = InMemoryURLRepository()
    test_cache = LRUCache(capacity=10)
    test_limiter = SlidingWindowRateLimiter(requests=50, window_seconds=60)

    def override_get_repository():
        return test_repo

    def override_get_global_cache():
        return test_cache

    def override_get_rate_limiter():
        return test_limiter

    def override_get_url_service():
        return URLService(repository=test_repo, cache=test_cache, base_url="http://testserver")

    app.dependency_overrides[get_repository] = override_get_repository
    app.dependency_overrides[get_global_cache] = override_get_global_cache
    app.dependency_overrides[get_rate_limiter] = override_get_rate_limiter
    app.dependency_overrides[get_url_service] = override_get_url_service

    yield {
        "repo": test_repo,
        "cache": test_cache,
        "limiter": test_limiter,
    }

    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_endpoint(client: TestClient):
    """Verify /health returns 200 and expected schema keys."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "cache_size" in data
    assert "cache_capacity" in data
    assert "database" in data
    assert "environment" in data


def test_cache_stats_endpoint(client: TestClient):
    """Verify GET /api/cache/stats returns live cache metrics."""
    response = client.get("/api/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["capacity"] == 10
    assert "current_size" in data
    assert "total_gets" in data
    assert "hits" in data
    assert "misses" in data
    assert "evictions" in data
    assert "hit_rate" in data


def test_create_short_url_api_success(client: TestClient):
    """Verify POST /api/urls creates a new short URL successfully."""
    payload = {"url": "https://fastapi.tiangolo.com/tutorial/"}
    response = client.post("/api/urls", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "short_code" in data
    assert len(data["short_code"]) > 0
    assert data["original_url"] == payload["url"]
    assert data["short_url"] == f"http://testserver/{data['short_code']}"


def test_create_short_url_api_invalid_url(client: TestClient):
    """Verify POST /api/urls rejects invalid URL inputs with 422."""
    response = client.post("/api/urls", json={"url": "not-a-valid-url"})
    assert response.status_code == 422

    response_empty = client.post("/api/urls", json={"url": ""})
    assert response_empty.status_code == 422


def test_redirect_to_url_flow(client: TestClient):
    """Verify full creation and GET /{short_code} redirection flow."""
    target = "https://docs.python.org/3/library/functions.html"
    create_resp = client.post("/api/urls", json={"url": target})
    assert create_resp.status_code == 201
    short_code = create_resp.json()["short_code"]

    # Redirect GET request (follow_redirects=False to verify 307)
    redirect_resp = client.get(f"/{short_code}", follow_redirects=False)
    assert redirect_resp.status_code == 307
    assert redirect_resp.headers["location"] == target


def test_redirect_nonexistent_short_code(client: TestClient):
    """Verify GET /{short_code} returns 404 for unknown codes."""
    response = client.get("/nonexistent123", follow_redirects=False)
    assert response.status_code == 404
    assert "detail" in response.json()


def test_redirect_invalid_short_code_format(client: TestClient):
    """Verify GET /{short_code} returns 400 for malformed short codes."""
    response = client.get("/invalid!@#$code%^", follow_redirects=False)
    assert response.status_code == 400


def test_get_url_details_api(client: TestClient):
    """Verify GET /api/urls/{short_code} retrieves metadata."""
    target = "https://example.com/details-test"
    create_resp = client.post("/api/urls", json={"url": target})
    short_code = create_resp.json()["short_code"]

    info_resp = client.get(f"/api/urls/{short_code}")
    assert info_resp.status_code == 200
    data = info_resp.json()
    assert data["short_code"] == short_code
    assert data["original_url"] == target
    assert data["access_count"] >= 0


def test_api_rate_limiting_exceeded(client: TestClient):
    """Verify rate limiter blocks client with 429 and Retry-After header when threshold reached."""
    # Override with a low rate limit for testing
    strict_limiter = SlidingWindowRateLimiter(requests=2, window_seconds=10)
    app.dependency_overrides[get_rate_limiter] = lambda: strict_limiter

    # Request 1 -> 201
    r1 = client.post("/api/urls", json={"url": "https://test.com/1"})
    assert r1.status_code == 201

    # Request 2 -> 201
    r2 = client.post("/api/urls", json={"url": "https://test.com/2"})
    assert r2.status_code == 201

    # Request 3 -> 429 Too Many Requests
    r3 = client.post("/api/urls", json={"url": "https://test.com/3"})
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    assert int(r3.headers["Retry-After"]) >= 1
    assert "Rate limit exceeded" in r3.json()["detail"]


def test_health_not_rate_limited(client: TestClient):
    """Verify /health is excluded from rate limits even if API routes are exhausted."""
    strict_limiter = SlidingWindowRateLimiter(requests=1, window_seconds=10)
    app.dependency_overrides[get_rate_limiter] = lambda: strict_limiter

    # Exhaust limit
    client.post("/api/urls", json={"url": "https://test.com/limit"})

    # Health check still works
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"


def test_openapi_and_docs_available(client: TestClient):
    """Verify /docs and /openapi.json are accessible."""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    assert openapi_resp.json()["info"]["title"] == "CacheShort API"
