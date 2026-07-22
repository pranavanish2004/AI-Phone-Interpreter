"""
Redis broker dependency for api_gateway.

Why this is thin:
    The actual implementation (RedisStreamBroker) already lives in
    backend/shared/messaging - built in Phase 1 specifically so every
    service (including this one) reuses it rather than each service writing
    its own Redis client setup. This module's only job is to manage the
    connection lifecycle (connect at startup, disconnect at shutdown) and
    expose it via FastAPI dependency injection.
"""

from shared.messaging import MessageBroker, RedisStreamBroker

from app.core.config import get_settings

settings = get_settings()

_broker = RedisStreamBroker(redis_url=str(settings.redis_url))


async def connect_broker() -> None:
    """Called once during FastAPI's startup lifespan (see main.py)."""
    await _broker.connect()


async def disconnect_broker() -> None:
    """Called once during FastAPI's shutdown lifespan (see main.py)."""
    await _broker.disconnect()


def get_broker() -> MessageBroker:
    """
    FastAPI dependency. Typed as the ABSTRACT `MessageBroker`, not the
    concrete `RedisStreamBroker` - route handlers and services that depend
    on this should only ever know about the interface, consistent with the
    Dependency Inversion decision made in Phase 1.
    """
    return _broker


async def check_redis_connection() -> bool:
    """Used by the upgraded /health endpoint to verify Redis reachability."""
    try:
        # ping() isn't part of the abstract MessageBroker interface (it's
        # Redis-specific), so we reach into the concrete client directly
        # here. This is the one deliberate exception to "only depend on the
        # abstraction" - health checks legitimately need to verify the real
        # underlying connection, not just the interface contract.
        await _broker._require_client().ping()  # noqa: SLF001
        return True
    except Exception:
        return False
