# Phase 3: FastAPI Backend (api_gateway Application Layer)

## What Was Built

- `core/config.py`: `Settings` (pydantic-settings), validated once at
  startup, cached via `lru_cache`. Normalizes `postgresql://` URLs to
  `postgresql+asyncpg://` for SQLAlchemy's async driver.
- `core/database.py`: async SQLAlchemy engine (pool_size=10,
  pool_pre_ping=True, 5s connect timeout), `Base` declarative class, and
  `get_db_session()` FastAPI dependency implementing session-per-request
  with rollback-on-error.
- `core/redis.py`: lifecycle wrapper (`connect_broker`/`disconnect_broker`)
  around Phase 1's `RedisStreamBroker`, plus a `get_broker()` DI provider
  typed as the abstract `MessageBroker`.
- `core/exceptions.py` + `core/exception_handlers.py`: `AppException`
  hierarchy (`NotFoundError`, `ValidationError`, `ConflictError`,
  `UnauthorizedError`, `ForbiddenError`, `ServiceUnavailableError`) mapped
  to a single consistent JSON error shape:
  `{"error_code", "message", "details"}`. Unhandled exceptions are caught
  by a catch-all handler that logs the full stack trace internally but
  NEVER leaks internal details to the client.
- `core/logging_middleware.py`: generates a `request_id` per request,
  attaches it as an `X-Request-ID` response header, logs request
  start/complete with duration - foundation for tracing a single action
  across multiple services in later phases.
- `core/security.py`: intentionally near-empty placeholder documenting
  exactly what Phase 4 adds, rather than a fake/guessed implementation.
- `api/health.py`: upgraded health check - verifies real DB and Redis
  connectivity (not just "process is running"), returns 503 when degraded,
  reports per-dependency status.
- `api/v1/router.py`: empty aggregator ready for Phase 4's `/auth` routes.
- `repositories/base.py`: generic `BaseRepository[ModelType]` with
  `get_by_id`/`add`/`delete`, ready for Phase 4's `UserRepository`.
- `main.py`: rewritten as an app factory (`create_app()`) with a `lifespan`
  that connects to Redis at startup (fail-fast) and disconnects at
  shutdown.
- **Shared logging upgrade**: `shared/logging/config.py`'s `JSONFormatter`
  changed from a fixed field whitelist to a denylist of Python's built-in
  `LogRecord` attributes, so every phase can attach new `extra={}` fields
  (like this phase's `request_id`, `duration_ms`) without editing shared
  code again. Verified backward-compatible with Phase 1's usage.
- Tests: `test_health.py`, `test_exception_handlers.py` - all passing.

## Key Decisions

| Decision | Choice | Reasoning |
|---|---|---|
| DB driver | Async (asyncpg) | Sync DB calls would block the event loop during call signaling's hot path |
| Error contract | Typed `AppException` -> one JSON shape | Flutter's `Failure` hierarchy (Phase 2) maps cleanly onto `error_code` regardless of which layer raised it |
| API versioning | `/api/v1/...` from day one | Cheap now, painful to retrofit after clients ship |
| Health check location | Root `/health`, NOT `/api/v1/health` | Infra checks are version-independent; avoids breaking Phase 1/2's existing `/health` consumers on every version bump |
| Startup behavior | Fail fast on Redis unreachable | Verified live: a genuinely unreachable Redis raises `ConnectionError` at container startup, not a silent later failure |

## Verified, Not Just Written

Since Docker isn't available in this sandbox, Phase 3 was validated by
actually running the code:
- `pytest tests/` -> 7/7 passing
- Live startup test against **no** Redis running -> confirmed fail-fast
  `ConnectionError` at startup, as designed
- Live startup test against a **real local Redis** (installed via apt for
  this verification) -> confirmed clean startup, and `/health` correctly
  reported `{"database": "unreachable", "redis": "ok"}` with a 503 - proving
  the endpoint distinguishes per-dependency status rather than a single
  pass/fail flag
- Request logging middleware confirmed emitting structured JSON logs with
  `request_id` correlation and `duration_ms` on every request

Postgres could not be installed via apt in this sandbox (mirror issue,
unrelated to project code) to complete the fully-healthy-response
verification locally - the real deployment path uses the official
`postgres:16-alpine` Docker image via docker-compose (Phase 1), a different
and unaffected path. Verify with:
```bash
docker compose -f docker/docker-compose.yml --env-file .env up --build
curl http://localhost:8000/health
# expect: {"service":"api_gateway","status":"ok","dependencies":{"database":"ok","redis":"ok"}}
```

## Open Items for Later Phases

- `database/migrations/` (Alembic) is installed as a dependency but not yet
  initialized - Phase 4 introduces the first real model (`User`), which is
  the natural point to run `alembic init` and generate the first migration.
- `get_db_session` and `get_broker` DI providers exist but have no
  consumers yet - Phase 4's `UserRepository` and auth routes are the first
  real usage.
- Auth-specific settings (`jwt_secret_key`, etc.) are validated in
  `Settings` but unused until Phase 4 implements `core/security.py`.

## How to Verify This Phase

```bash
cd backend/api_gateway
pip install -r requirements.txt
export PYTHONPATH=".:.."   # so `app` and `shared` both resolve
pytest tests/ -v
```

Or, full stack:
```bash
docker compose -f docker/docker-compose.yml --env-file .env up --build api_gateway postgres redis
curl http://localhost:8000/health
```
