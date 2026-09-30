"""Unit tests for URLService layer, LRU cache integration, and collision races."""

from unittest.mock import MagicMock
import pytest

from app.cache.lru_cache import LRUCache
from app.database.repository import DuplicateShortCodeError, InMemoryURLRepository
from app.services.url_service import URLService, ShortCodeGenerationError


@pytest.fixture
def memory_repo() -> InMemoryURLRepository:
    return InMemoryURLRepository()


@pytest.fixture
def lru_cache() -> LRUCache:
    return LRUCache(capacity=5)


@pytest.fixture
def service(memory_repo: InMemoryURLRepository, lru_cache: LRUCache) -> URLService:
    return URLService(repository=memory_repo, cache=lru_cache, base_url="http://testserver")


def test_create_short_url_success(service: URLService, lru_cache: LRUCache, memory_repo: InMemoryURLRepository):
    """Verify creating a short URL creates a database record and populates the cache."""
    target = "https://example.com/some/long/article"
    result = service.create_short_url(target)

    assert "short_code" in result
    assert result["original_url"] == target
    assert result["short_url"] == f"http://testserver/{result['short_code']}"

    # Verify repository has record
    db_record = memory_repo.get_by_short_code(result["short_code"])
    assert db_record is not None
    assert db_record.original_url == target

    # Verify cache is populated
    assert lru_cache.get(result["short_code"]) == target


def test_resolve_short_code_cache_hit_zero_database_calls(service: URLService, lru_cache: LRUCache, memory_repo: InMemoryURLRepository):
    """Verify resolving a short code hits cache with ZERO database roundtrips (no query, no update)."""
    # Seed cache directly
    lru_cache.put("mycode", "https://cached-target.com")

    # Mock repository methods to strictly ensure NONE are called on cache hit
    memory_repo.get_by_short_code = MagicMock(return_value=None)
    memory_repo.increment_access = MagicMock()

    resolved = service.resolve_short_code("mycode")
    assert resolved == "https://cached-target.com"

    # Strict assertion: ZERO database calls on cache hit
    memory_repo.get_by_short_code.assert_not_called()
    memory_repo.increment_access.assert_not_called()


def test_resolve_short_code_cache_miss_db_hit(service: URLService, lru_cache: LRUCache, memory_repo: InMemoryURLRepository):
    """Verify cache miss queries the database, populates cache, and increments access count."""
    # Persist in repo directly without putting in cache
    record = memory_repo.create_url("dbcode", "https://database-target.com")

    assert lru_cache.get("dbcode") is None

    # First resolve: cache miss -> database lookup -> populate cache & update access
    resolved = service.resolve_short_code("dbcode")
    assert resolved == "https://database-target.com"

    # Now cache should have it
    assert lru_cache.get("dbcode") == "https://database-target.com"

    # Repository access count incremented on DB hit
    updated_record = memory_repo.get_by_short_code("dbcode")
    assert updated_record is not None
    assert updated_record.access_count == 1


def test_resolve_short_code_not_found(service: URLService, lru_cache: LRUCache):
    """Verify lookup of nonexistent short code returns None."""
    resolved = service.resolve_short_code("nonexistent")
    assert resolved is None
    assert lru_cache.get("nonexistent") is None


def test_collision_retry_handling_on_duplicate_constraint(service: URLService, memory_repo: InMemoryURLRepository):
    """Verify direct insert handles duplicate constraint violations with retries."""
    memory_repo.create_url("COLLID", "https://first.com")

    # Mock candidate generator to produce collision first, then fresh code
    codes = ["COLLID", "COLLID", "FRESH1"]
    service.generate_random_code = MagicMock(side_effect=codes)

    result = service.create_short_url("https://second.com")
    assert result["short_code"] == "FRESH1"
    assert service.generate_random_code.call_count == 3


def test_collision_retry_exhaustion_raises_error(service: URLService, memory_repo: InMemoryURLRepository):
    """Verify error is raised if all retry attempts collide on UNIQUE constraint."""
    memory_repo.create_url("COLLID", "https://first.com")

    # All attempts return existing code
    service.generate_random_code = MagicMock(return_value="COLLID")

    with pytest.raises(ShortCodeGenerationError, match="Failed to generate a unique short code"):
        service.create_short_url("https://second.com")
