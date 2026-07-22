"""
api_gateway application entry point.

This is now an "app factory" pattern: `create_app()` builds and configures
the FastAPI instance, and `app = create_app()` at module level is what
uvicorn actually serves (per the Dockerfile's
`uvicorn app.main:app` command). Splitting construction into a function
(rather than configuring a module-level `app` directly, as Phase 1's stub
did) makes it possible to construct a fresh, isolated app instance in tests
- important once we have real routes and want to test them without any
risk of shared state between test cases.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging_middleware import RequestLoggingMiddleware
from app.core.redis import connect_broker, disconnect_broker
from shared.logging import configure_logging

settings = get_settings()
configure_logging(service_name="api_gateway", level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown hook.

    Why connect to Redis here rather than lazily on first use: we want to
    fail fast at container startup if Redis is unreachable (surfacing
    clearly in `docker compose up` logs), rather than have the first
    request that happens to need Redis fail mysteriously minutes into
    running. The database engine doesn't need an equivalent explicit
    connect step - SQLAlchemy's async engine connects lazily per-session,
    and pool_pre_ping (set in database.py) already guards against handing
    out dead connections.
    """
    logger.info("api_gateway starting up", extra={"environment": settings.environment})
    await connect_broker()
    yield
    logger.info("api_gateway shutting down")
    await disconnect_broker()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Phone Interpreter - API Gateway",
        description="Auth, signaling, and orchestration for the AI Phone Interpreter backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    # Health check mounted at root (see api/v1/router.py docstring for why
    # it's not versioned).
    app.include_router(health_router)

    # All future business routes (auth, profile, calls, ...) are versioned.
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
