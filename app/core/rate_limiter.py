"""Lightweight, process-local Sliding Window Rate Limiter."""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple
from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Thread-safe process-local sliding window rate limiter."""

    def __init__(
        self,
        requests: int = 100,
        window_seconds: int = 60,
        enabled: bool = True,
        cleanup_interval_seconds: float = 60.0,
    ):
        self.requests: int = requests
        self.window_seconds: int = window_seconds
        self.enabled: bool = enabled
        self.cleanup_interval_seconds: float = cleanup_interval_seconds

        self._records: Dict[str, List[float]] = {}
        self._lock: threading.Lock = threading.Lock()
        self._last_cleanup: float = time.time()

    def is_allowed(self, client_id: str) -> Tuple[bool, int]:
        """Check if request from client_id is allowed within sliding window.

        Returns (is_allowed, retry_after_seconds).
        """
        if not self.enabled:
            return True, 0

        with self._lock:
            now = time.time()

            # Periodic cleanup of completely expired entries
            if now - self._last_cleanup > self.cleanup_interval_seconds:
                self._prune_expired(now)

            window_start = now - self.window_seconds
            timestamps = self._records.get(client_id, [])

            # Filter out timestamps outside the active sliding window
            filtered = [ts for ts in timestamps if ts > window_start]

            if len(filtered) >= self.requests:
                # Calculate retry-after based on oldest timestamp in active window
                oldest_in_window = filtered[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now + 0.999))
                self._records[client_id] = filtered
                return False, retry_after

            filtered.append(now)
            self._records[client_id] = filtered
            return True, 0

    def _prune_expired(self, now: float) -> None:
        """Remove old records where all timestamps fall outside the sliding window."""
        cutoff = now - self.window_seconds
        stale_keys = []
        for client_id, timestamps in self._records.items():
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if not valid_timestamps:
                stale_keys.append(client_id)
            else:
                self._records[client_id] = valid_timestamps

        for key in stale_keys:
            del self._records[key]

        self._last_cleanup = now
        logger.debug("Pruned expired rate limiter records. Active clients: %d", len(self._records))

    def reset(self) -> None:
        """Reset all rate limiter state (used in tests)."""
        with self._lock:
            self._records.clear()
            self._last_cleanup = time.time()


# Global rate limiter instance
_global_rate_limiter: Optional[SlidingWindowRateLimiter] = None


def get_rate_limiter(settings: Settings = Depends(get_settings)) -> SlidingWindowRateLimiter:
    """Retrieve or initialize the global rate limiter instance."""
    global _global_rate_limiter
    if (
        _global_rate_limiter is None
        or _global_rate_limiter.requests != settings.rate_limit_requests
        or _global_rate_limiter.window_seconds != settings.rate_limit_window_seconds
        or _global_rate_limiter.enabled != settings.rate_limit_enabled
    ):
        _global_rate_limiter = SlidingWindowRateLimiter(
            requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
            enabled=settings.rate_limit_enabled,
        )
    return _global_rate_limiter


def rate_limit_dependency(
    request: Request,
    limiter: SlidingWindowRateLimiter = Depends(get_rate_limiter),
) -> None:
    """FastAPI route dependency to enforce rate limiting."""
    client_host = request.client.host if request.client else "unknown"
    # Handle X-Forwarded-For if present
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_host = forwarded.split(",")[0].strip()

    allowed, retry_after = limiter.is_allowed(client_host)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please retry in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
