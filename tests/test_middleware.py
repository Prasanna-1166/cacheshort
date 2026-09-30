"""Unit and integration tests for observability middleware, request timing, structured logging, and uptime."""

import json
import logging
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.middleware import SAFE_REQUEST_ID_PATTERN
from app.core.security import generate_api_key, API_KEY_HEADER_NAME
from app.database.api_key_repository import InMemoryAPIKeyRepository, get_api_key_repository
from app.database.repository import InMemoryURLRepository, get_repository
from app.cache.lru_cache import LRUCache
from app.core.rate_limiter import SlidingWindowRateLimiter, get_rate_limiter
from app.services.url_service import URLService, get_url_service, get_global_cache
from benchmarks.benchmark_http import calculate_percentiles


@pytest.fixture
def obs_environment():
    """Setup test dependencies."""
    key_repo = InMemoryAPIKeyRepository()
    url_repo = InMemoryURLRepository()
    cache = LRUCache(capacity=10)
    limiter = SlidingWindowRateLimiter(requests=100, window_seconds=60)

    raw_key, prefix, key_hash = generate_api_key()
    key_repo.create_api_key(name="obs-key", key_prefix=prefix, key_hash=key_hash)

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
        "raw_key": raw_key,
        "cache": cache,
    }

    app.dependency_overrides.clear()


@pytest.fixture
def client(obs_environment) -> TestClient:
    return TestClient(app)


def test_process_time_header_exists_and_is_numeric(client: TestClient):
    """Verify X-Process-Time is attached to responses and contains a valid float."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Process-Time" in response.headers

    process_time = float(response.headers["X-Process-Time"])
    assert process_time >= 0.0


def test_request_id_generated_and_propagated(client: TestClient):
    """Verify X-Request-ID is generated and returned when not provided by client."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    req_id = response.headers["X-Request-ID"]
    assert len(req_id) > 10
    assert SAFE_REQUEST_ID_PATTERN.match(req_id) is not None


def test_incoming_safe_request_id_preserved(client: TestClient):
    """Verify valid client-supplied X-Request-ID is preserved and returned."""
    custom_id = "custom-req-trace-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_incoming_malformed_request_id_replaced(client: TestClient):
    """Verify unsafe client-supplied X-Request-ID is sanitized with a generated UUID."""
    unsafe_id = "invalid<script>alert(1)</script>id"
    response = client.get("/health", headers={"X-Request-ID": unsafe_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != unsafe_id
    assert SAFE_REQUEST_ID_PATTERN.match(response.headers["X-Request-ID"]) is not None


def test_health_endpoint_exposes_uptime(client: TestClient):
    """Verify /health returns uptime_seconds as a non-negative float."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0.0


def test_structured_json_logging_emits_valid_json(client: TestClient, caplog):
    """Verify structured log messages are machine-readable JSON containing expected keys."""
    with caplog.at_level(logging.INFO, logger="cacheshort.access"):
        client.get("/health")

    access_records = [r for r in caplog.records if r.name == "cacheshort.access"]
    assert len(access_records) >= 1

    last_record = access_records[-1]
    log_data = json.loads(last_record.getMessage())

    assert "timestamp" in log_data
    assert "request_id" in log_data
    assert log_data["method"] == "GET"
    assert log_data["path"] == "/health"
    assert log_data["status_code"] == 200
    assert "duration_ms" in log_data
    assert "client_ip" in log_data


def test_structured_logs_do_not_contain_secrets(client: TestClient, obs_environment, caplog):
    """Verify secrets (X-API-Key and Bearer tokens) are never leaked into log output."""
    raw_key = obs_environment["raw_key"]
    fake_token = "secret-bearer-token-12345"

    headers = {
        API_KEY_HEADER_NAME: raw_key,
        "Authorization": f"Bearer {fake_token}",
    }

    with caplog.at_level(logging.INFO, logger="cacheshort.access"):
        client.post("/api/urls", json={"url": "https://example.com/obs-test"}, headers=headers)

    for record in caplog.records:
        msg = record.getMessage()
        assert raw_key not in msg, "Raw API key found in log output!"
        assert fake_token not in msg, "Authorization token found in log output!"


def test_benchmark_percentile_calculations():
    """Verify calculate_percentiles correctly computes statistics across distributions."""
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    stats = calculate_percentiles(latencies)

    assert stats["min_ms"] == 10.0
    assert stats["max_ms"] == 100.0
    assert stats["mean_ms"] == 55.0
    assert stats["median_ms"] == 60.0
    assert stats["p90_ms"] == 100.0

    # Empty list handling
    empty_stats = calculate_percentiles([])
    assert empty_stats["mean_ms"] == 0.0
    assert empty_stats["median_ms"] == 0.0
