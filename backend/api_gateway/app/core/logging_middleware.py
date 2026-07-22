"""
Request logging middleware.

Why a correlation ID (`request_id`) matters here specifically:
    In later phases, a single user action (e.g. "start a call") triggers
    requests across MULTIPLE services - api_gateway, then messages flowing
    through audio/speech/translation/tts services via Redis Streams. If
    something goes wrong, being able to grep logs across all of them for
    one `request_id` (or `call_id`, once calls exist) is the difference
    between a five-minute debug session and an hour of guessing. We
    generate the ID here, log it on every request, and it's designed to be
    threaded through to downstream services in later phases (e.g. attached
    to Redis Stream messages).
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.monotonic()
        logger.info(
            "request started",
            extra={"request_id": request_id, "path": request.url.path, "method": request.method},
        )

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
