import time
from fastapi import APIRouter, Depends
from app.cache.lru_cache import LRUCache
from app.core.config import Settings, get_settings
from app.database.connection import DatabaseManager
from app.schemas.url import HealthResponse
from app.services.url_service import get_global_cache

router = APIRouter(tags=["Health"])

_PROCESS_START_TIME: float = time.monotonic()


def get_uptime_seconds() -> float:
    """Calculate process uptime in seconds since initialization."""
    return round(time.monotonic() - _PROCESS_START_TIME, 2)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Health Status",
    description="Returns service health, LRU cache metrics, database connectivity status, and process uptime.",
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
        uptime_seconds=get_uptime_seconds(),
    )

