"""Health and readiness check endpoints."""

from fastapi import APIRouter, Depends
from app.cache.lru_cache import LRUCache
from app.core.config import Settings, get_settings
from app.database.connection import DatabaseManager
from app.schemas.url import HealthResponse
from app.services.url_service import get_global_cache

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Health Status",
    description="Returns service health, LRU cache metrics, and database connectivity status.",
)
def check_health(
    settings: Settings = Depends(get_settings),
    cache: LRUCache = Depends(get_global_cache),
) -> HealthResponse:
    """Return application health information without failing unconditionally if DB is offline."""
    if settings.database_url is None:
        db_status = "not_configured"
    else:
        db_healthy = DatabaseManager.check_health()
        db_status = "healthy" if db_healthy else "unreachable"

    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        cache_size=cache.size(),
        cache_capacity=cache.capacity,
        database=db_status,
    )
