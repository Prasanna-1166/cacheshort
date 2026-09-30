"""Unit and API tests for URL Analytics statistics endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.repository import InMemoryURLRepository, get_repository
from app.cache.lru_cache import LRUCache
from app.services.url_service import get_global_cache, URLService, get_url_service


@pytest.fixture
def test_env():
    test_repo = InMemoryURLRepository()
    test_cache = LRUCache(capacity=10)

    def override_get_repository():
        return test_repo

    def override_get_global_cache():
        return test_cache

    def override_get_url_service():
        return URLService(repository=test_repo, cache=test_cache, base_url="http://testserver")

    app.dependency_overrides[get_repository] = override_get_repository
    app.dependency_overrides[get_global_cache] = override_get_global_cache
    app.dependency_overrides[get_url_service] = override_get_url_service

    yield {"repo": test_repo, "cache": test_cache}

    app.dependency_overrides.clear()


@pytest.fixture
def client(test_env) -> TestClient:
    return TestClient(app)


def test_get_url_stats_success(client: TestClient):
    """Verify GET /api/urls/{short_code}/stats returns accurate analytics schema."""
    target = "https://example.com/analytics-target"
    create_resp = client.post("/api/urls", json={"url": target})
    assert create_resp.status_code == 201
    short_code = create_resp.json()["short_code"]

    stats_resp = client.get(f"/api/urls/{short_code}/stats")
    assert stats_resp.status_code == 200
    data = stats_resp.json()

    assert data["short_code"] == short_code
    assert data["original_url"] == target
    assert "created_at" in data
    assert "last_accessed_at" in data
    assert data["access_count"] >= 0


def test_get_url_stats_not_found(client: TestClient):
    """Verify GET /api/urls/{short_code}/stats returns 404 for unknown code."""
    response = client.get("/api/urls/unknown999/stats")
    assert response.status_code == 404
    assert response.json()["detail"] == "Short code not found"


def test_get_url_stats_invalid_format(client: TestClient):
    """Verify GET /api/urls/{short_code}/stats returns 400 for malformed code."""
    response = client.get("/api/urls/invalid!!code/stats")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid short code format"
