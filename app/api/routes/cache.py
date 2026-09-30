"""Cache observability endpoints."""

from fastapi import APIRouter, Depends
from app.cache.lru_cache import LRUCache
from app.core.security import verify_api_key
from app.schemas.cache import CacheStatsResponse
from app.services.url_service import get_global_cache

router = APIRouter(prefix="/api/cache", tags=["Cache Metrics"])


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

