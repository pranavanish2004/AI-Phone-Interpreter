"""
Application-level exception hierarchy.

Why not just raise fastapi.HTTPException everywhere:
    HTTPException is fine for simple cases, but as soon as we have
    business/service logic that doesn't know about HTTP at all (e.g. a
    repository method, or in later phases a translation-context builder),
    we don't want that layer importing FastAPI just to raise an error - that
    couples pure business logic to the web framework. Instead, business
    logic raises these AppException subtypes, and ONE place (exception
    handlers, registered in main.py) translates them into HTTP responses.

    This also gives the Flutter client a STABLE, predictable error contract:
    every error response has the same shape:
        { "error_code": "...", "message": "...", "details": {...} }
    regardless of which service or which layer raised it. The Flutter
    `Failure` hierarchy from Phase 2 maps onto `error_code` cleanly.
"""

from typing import Any


class AppException(Exception):
    """Base class for all deliberately-raised, "expected" application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    status_code = 404
    error_code = "NOT_FOUND"


class ValidationError(AppException):
    """
    For business-rule validation failures (e.g. "phone number already
    registered to a different account") - distinct from Pydantic's own
    request-schema validation, which FastAPI handles automatically before
    our code even runs.
    """
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ConflictError(AppException):
    """E.g. attempting to create a resource that already exists."""
    status_code = 409
    error_code = "CONFLICT"


class UnauthorizedError(AppException):
    """Missing or invalid credentials - used from Phase 4 onward."""
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    """Valid credentials, but insufficient permission for the action."""
    status_code = 403
    error_code = "FORBIDDEN"


class ServiceUnavailableError(AppException):
    """
    A downstream dependency (DB, Redis, or another microservice) is
    unreachable. Distinct from a 500 because it signals to the client
    "retry later", not "something is broken in the code".
    """
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
