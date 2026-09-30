import time
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from app.cache.lru_cache import LRUCache
from app.core.config import Settings, get_settings
from app.database.connection import DatabaseManager
from app.schemas.url import HealthResponse, ReadinessResponse
from app.services.url_service import get_global_cache

router = APIRouter(tags=["Health"])

_PROCESS_START_TIME: float = time.monotonic()


def get_uptime_seconds() -> float:
    """Calculate process uptime in seconds since initialization."""
    return round(time.monotonic() - _PROCESS_START_TIME, 2)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Liveness Health Status",
    description="Shallow in-memory liveness check returning process status, LRU cache metrics, and uptime with zero database calls.",
)
def check_liveness(
    settings: Settings = Depends(get_settings),
    cache: LRUCache = Depends(get_global_cache),
) -> HealthResponse:
    """Return in-memory application liveness without querying PostgreSQL."""
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        cache_size=cache.size(),
        cache_capacity=cache.capacity,
        database=None,
        uptime_seconds=get_uptime_seconds(),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Application Database Readiness Probe",
    description="Deep readiness probe actively validating PostgreSQL database connectivity and pool health.",
    responses={
        200: {"description": "Application and database are ready to serve traffic"},
        503: {"description": "Database connectivity is degraded or uninitialized"},
    },
)
def check_readiness(
    settings: Settings = Depends(get_settings),
) -> Response:
    """Validate live database connectivity via connection pool."""
    uptime = get_uptime_seconds()
    db_healthy = DatabaseManager.check_health()

    if db_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=ReadinessResponse(
                status="ok",
                environment=settings.app_env,
                database="healthy",
                uptime_seconds=uptime,
            ).model_dump(),
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ReadinessResponse(
            status="degraded",
            environment=settings.app_env,
            database="unavailable",
            uptime_seconds=uptime,
        ).model_dump(),
    )


