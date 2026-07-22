"""
Async database engine and session management.

Why async SQLAlchemy (not the sync version) here:
    This service will, in later phases, sit in the hot path of call
    signaling - every WebSocket message potentially triggers a DB read/write
    (e.g. logging a conversation turn). A sync DB call would block the
    entire event loop for that duration, stalling every other concurrent
    call being handled by the same worker process. Async SQLAlchemy +
    asyncpg lets the event loop serve other requests while waiting on I/O.

Why a session-per-request pattern via `Depends(get_db_session)`:
    This is the standard, safe pattern for FastAPI + SQLAlchemy: each
    request gets its own session, which is closed automatically when the
    request finishes (success or failure) via the `async with` block. This
    prevents two different requests from ever accidentally sharing a
    session/transaction, which is a source of very confusing bugs.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# echo=True in dev logs every SQL statement - invaluable while building
# repositories in Phase 4+, disabled in production because it's verbose and
# can leak data into logs.
engine = create_async_engine(
    settings.sqlalchemy_database_url,
    echo=not settings.is_production,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,  # detects and discards dead connections (e.g. after
                          # a DB restart) instead of handing out broken ones
    connect_args={"timeout": 5},  # fail fast (5s) instead of hanging when
                                   # the DB is unreachable - matters both for
                                   # the /health readiness check responding
                                   # promptly and for tests run without a
                                   # real Postgres available
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    # expire_on_commit=False: without this, accessing a model attribute
    # after commit() triggers a fresh DB round-trip (SQLAlchemy's default
    # safety behavior). We disable it because in an async context that
    # implicit lazy-load can happen outside the session's async context and
    # raise a confusing error - we'd rather be explicit about refreshing
    # objects when we actually need post-commit fresh data.
)


class Base(DeclarativeBase):
    """Base class every ORM model (Phase 4+) inherits from."""
    pass


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a request-scoped session.

    Usage in a route:
        @router.get("/users/{id}")
        async def get_user(id: str, db: AsyncSession = Depends(get_db_session)):
            ...

    The try/except/finally ensures that if a route handler raises, the
    session is rolled back (not left holding a half-committed transaction)
    before being closed.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """Used by the upgraded /health endpoint to verify DB reachability."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
