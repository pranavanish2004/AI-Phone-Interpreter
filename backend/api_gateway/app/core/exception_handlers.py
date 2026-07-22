"""
FastAPI exception handlers - the ONE place where our internal exception
hierarchy gets translated into HTTP JSON responses.

Registered once in main.py via `register_exception_handlers(app)`.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def _error_response(status_code: int, error_code: str, message: str, details: dict) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message, "details": details},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        # 5xx-class AppExceptions (e.g. ServiceUnavailableError) are logged
        # at ERROR since they indicate infrastructure problems worth
        # alerting on; 4xx-class ones (NotFoundError, ValidationError) are
        # normal client-facing outcomes and logged at INFO to avoid
        # drowning real errors in noise.
        log_level = logging.ERROR if exc.status_code >= 500 else logging.INFO
        logger.log(
            log_level,
            "%s: %s",
            exc.error_code,
            exc.message,
            extra={"error_code": exc.error_code, "path": str(request.url.path)},
        )
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Catches Pydantic request-schema validation failures (e.g. a client
        sends `preferred_language: 123` instead of a string) BEFORE our
        route code even runs. Without this handler, FastAPI's default
        422 response has a different JSON shape than our AppException
        responses - this handler normalizes it to match, so the Flutter
        client only needs ONE error-parsing code path.
        """
        logger.info("Request validation failed: %s", exc.errors())
        # jsonable_encoder is required here, not optional: Pydantic's
        # exc.errors() can embed the raw ValueError instance itself (under
        # error['ctx']['error']) when a custom @field_validator raises
        # ValueError - plain json.dumps cannot serialize an exception
        # object and would crash INSIDE the error handler itself, turning
        # a clean 422 into an unhandled 500. jsonable_encoder converts it
        # to a JSON-safe string representation.
        safe_errors = jsonable_encoder(exc.errors())
        # Using the raw integer (422) rather than status.HTTP_422_* here
        # deliberately: Starlette renamed this constant between versions
        # (HTTP_422_UNPROCESSABLE_ENTITY -> HTTP_422_UNPROCESSABLE_CONTENT),
        # and the integer value is stable across all of them.
        return _error_response(
            422,
            "REQUEST_VALIDATION_ERROR",
            "The request contained invalid data.",
            {"errors": safe_errors},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        """
        Last-resort catch-all. This should be rare - if it fires often, it
        means a real bug is being surfaced as a generic 500 instead of a
        specific AppException, and the logged stack trace here is exactly
        what you need to go fix that.

        Critically: we NEVER include `str(exc)` in the response body sent
        to the client. Internal exception messages can leak implementation
        details (stack traces, SQL, file paths) - the client gets a generic
        message, the FULL detail goes only to our own logs.
        """
        logger.error(
            "Unhandled exception on %s",
            request.url.path,
            exc_info=exc,
        )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again.",
            {},
        )
