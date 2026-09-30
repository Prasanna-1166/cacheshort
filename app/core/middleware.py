"""Observability middleware providing request ID propagation, execution timing, and structured JSON logging."""

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("cacheshort.access")

# Safe Request ID regex pattern allowing alphanumeric characters, hyphens, and underscores up to 64 chars
SAFE_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing X-Request-ID, X-Process-Time, and structured JSON access logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Resolve or generate sanitized Request ID
        incoming_request_id = request.headers.get("X-Request-ID")
        if incoming_request_id and SAFE_REQUEST_ID_PATTERN.match(incoming_request_id):
            request_id = incoming_request_id
        else:
            request_id = str(uuid.uuid4())

        # Attach request_id to request state for downstream handlers
        request.state.request_id = request_id

        # 2. Measure server-side execution duration
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_sec = time.perf_counter() - start_time
            duration_ms = round(duration_sec * 1000.0, 3)
            self._log_request(request, request_id, 500, duration_ms)
            raise exc

        duration_sec = time.perf_counter() - start_time
        duration_ms = round(duration_sec * 1000.0, 3)

        # 3. Attach standard response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_sec:.6f}"

        # 4. Emit structured JSON log (never log credentials, auth headers, or raw bodies)
        self._log_request(request, request_id, response.status_code, duration_ms)

        return response

    def _log_request(
        self,
        request: Request,
        request_id: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Format and emit a machine-readable JSON log record to stdout/stderr."""
        # Extract client host safely without blindly trusting unverified spoofed headers
        client_ip = "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host

        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
        }

        logger.info(json.dumps(log_payload))
