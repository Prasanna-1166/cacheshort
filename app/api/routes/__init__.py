"""API routes package."""
from app.api.routes.health import router as health_router
from app.api.routes.urls import router as urls_router
from app.api.routes.cache import router as cache_router

__all__ = ["health_router", "urls_router", "cache_router"]
