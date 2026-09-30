from fastapi import APIRouter, Depends
from app.cache.lru_cache import LRUCache
from app.core.security import verify_api_key
from app.schemas.cache import (
    CacheStatsResponse,
    CacheEvictionResponse,
    CacheClearResponse,
)
from app.services.url_service import get_global_cache

router = APIRouter(prefix="/api/cache", tags=["Cache Administration"])


@router.get(
    "/stats",
    response_model=CacheStatsResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Get LRU Cache Statistics",
    description="Returns observability metrics for the custom in-memory LRU cache including hits, misses, evictions, and hit rate.",
)
def get_cache_stats(
    cache: LRUCache = Depends(get_global_cache),
) -> CacheStatsResponse:
    """Return live snapshot of LRU cache metrics."""
    return CacheStatsResponse(**cache.stats())


@router.delete(
    "/entries/{short_code}",
    response_model=CacheEvictionResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Evict Single Cache Entry",
    description="Remove a specific short code mapping from LRU memory. Does not delete from PostgreSQL.",
)
def evict_cache_entry(
    short_code: str,
    cache: LRUCache = Depends(get_global_cache),
) -> CacheEvictionResponse:
    """Evict a specific short code from in-memory LRU cache."""
    evicted = cache.remove(short_code)
    message = f"Short code '{short_code}' evicted from cache" if evicted else f"Short code '{short_code}' was not present in cache"
    return CacheEvictionResponse(
        short_code=short_code,
        evicted=evicted,
        message=message,
    )


@router.post(
    "/clear",
    response_model=CacheClearResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Clear Entire LRU Cache",
    description="Flush all entries from in-memory LRU cache without resetting historical hit/miss/eviction counters.",
)
def clear_cache(
    cache: LRUCache = Depends(get_global_cache),
) -> CacheClearResponse:
    """Flush all in-memory entries from LRU cache."""
    entries_count = cache.size()
    cache.clear()
    return CacheClearResponse(
        cleared_entries=entries_count,
        message=f"Cache cleared successfully. Evicted {entries_count} in-memory entries.",
    )


