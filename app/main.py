import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.routes import health_router, urls_router, cache_router, api_keys_router
from app.core.config import get_settings
from app.core.middleware import ObservabilityMiddleware
from app.database.connection import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cacheshort")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for database connection pool setup and teardown."""
    settings = get_settings()
    logger.info("Starting CacheShort service in '%s' environment...", settings.app_env)

    # Initialize connection pool if database_url is provided
    if settings.database_url:
        try:
            DatabaseManager.initialize_pool(settings.database_url)
        except Exception as e:
            logger.error("Could not connect to PostgreSQL database on startup: %s", e)
            raise
    elif settings.app_env.lower() not in ("test", "testing"):
        error_msg = (
            "DATABASE_URL environment variable is required to run CacheShort in "
            f"'{settings.app_env}' mode. In-memory repository fallback is restricted to test environments."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    else:
        logger.info("Running in test environment with test database configuration.")

    yield

    logger.info("Shutting down CacheShort service...")
    DatabaseManager.close_pool()


app = FastAPI(
    title="CacheShort API",
    description="High-performance, LRU-Cache-Backed URL Shortener using custom O(1) Doubly Linked List + HashMap cache with PostgreSQL persistence.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Register Observability & Timing Middleware
app.add_middleware(ObservabilityMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safe production exception handler preventing credential/internal trace leakage."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    error_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "event": "unhandled_server_exception",
        "method": request.method,
        "path": request.url.path,
        "error_type": type(exc).__name__,
    }
    logger.error(json.dumps(error_payload))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
        headers={"X-Request-ID": request_id},
    )


# Include Routers (specific path prefixes first)
app.include_router(health_router)
app.include_router(cache_router)
app.include_router(api_keys_router)
app.include_router(urls_router)


