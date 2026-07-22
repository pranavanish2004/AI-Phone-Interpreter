# Phase 4: Authentication

## What Was Built

**Backend (`api_gateway`):**
- `models/user.py`: SQLAlchemy `User` model mirroring `schema.sql`.
- `schemas/auth.py`: request/response schemas with India phone-number
  normalization/validation (`+91XXXXXXXXXX`, must start 6-9).
- `core/security.py`: JWT creation/decoding + `get_current_user_id`
  dependency - replaces Phase 3's documented placeholder.
- `services/otp_provider.py`: `OTPProvider` interface + `DevOTPProvider`
  (logs OTP instead of sending real SMS) - swappable for MSG91/Twilio later.
- `services/otp_store.py`: Redis-backed OTP storage with TTL and
  single-use consumption (deliberately NOT using the Phase 1
  `MessageBroker` abstraction - simple key-value with expiry is a different
  need than event streaming).
- `services/auth_service.py`: business logic - request/verify OTP, handles
  both registration and login through one endpoint (avoids a phone-number
  enumeration side channel).
- `repositories/user_repository.py`, `api/v1/auth/{dependencies,routes}.py`:
  full wiring, `POST /otp/request`, `POST /otp/verify`, `GET /me`.
- Alembic initialized (`migrations/`), baseline migration for `users`
  hand-written to match `schema.sql` exactly (autogenerate needs a live DB
  to diff against, unavailable in this sandbox - see below).

**Flutter (`mobile`):**
- `features/auth/domain/`: `UserEntity`, abstract `AuthRepository`.
- `features/auth/data/`: `UserModel` (manual JSON mapping, no codegen yet),
  `TokenStorageService` (flutter_secure_storage), `AuthRepositoryImpl`
  (maps backend `error_code` values onto Phase 2's `Failure` hierarchy).
- `core/di/dio_provider.dart`: real auth-token interceptor, replacing the
  Phase 3 placeholder.
- `features/auth/presentation/`: `AuthNotifier` (AsyncNotifier), phone
  entry screen, OTP verify screen, minimal authenticated home screen.
- `core/router/app_router.dart`: real `redirect` guard using
  `authNotifierProvider`'s state - replaces the Phase 2 placeholder.

## Bugs Found and Fixed During Testing (not just written, verified)

1. **Non-JSON-serializable validation errors**: Pydantic's `exc.errors()`
   can embed a raw `ValueError` instance (under `ctx.error`) when a custom
   `@field_validator` raises `ValueError` - `json.dumps` crashed on this,
   turning a clean 422 into an unhandled 500. Fixed with
   `fastapi.encoders.jsonable_encoder`.
2. **UUID/str schema mismatch**: `UserResponseSchema.id` was typed `str`,
   but the ORM returns a real `uuid.UUID` object - Pydantic's strict
   validation rejected it. Fixed by typing the field as `uuid.UUID`
   (Pydantic serializes it to a JSON string automatically).
3. **Test-harness bug, not app bug**: my first two attempts at the
   route-level integration test built a broken `get_auth_service` override
   that opened an independent, never-committed DB session. Root cause:
   FastAPI's per-request dependency cache is keyed by the *originally
   declared* callable at each `Depends()` site, evaluated *before*
   `dependency_overrides` substitution - not by the final resolved
   function. Verified via session-id debug instrumentation, then fixed by
   having the override depend on `Depends(get_db_session)` (matching
   production's own declaration) rather than a differently-named wrapper.

## Key Decisions

| Decision | Choice | Reasoning |
|---|---|---|
| Auth method | Phone + OTP, no password required | India-first UX; `password_hash` already nullable since Phase 1 |
| One endpoint for register+login | `POST /otp/verify` handles both | Avoids a "does this number exist" enumeration side channel |
| OTP storage | Redis, direct client access (not `MessageBroker`) | Simple TTL key-value is the wrong fit for a streaming abstraction |
| Flutter data models | Manual JSON mapping, no `json_serializable` yet | Shape is small/stable; codegen deferred until it earns its complexity cost |

## Verified, Not Just Written

- **23/23 backend tests passing**, including full HTTP-level integration
  tests (register -> verify -> access protected route -> reject
  missing/garbage tokens).
- Backend tests run against **in-memory SQLite** (`aiosqlite` +
  `StaticPool`), not Postgres - a real Postgres 16 package was unavailable
  via this sandbox's apt mirror (an infrastructure gap unrelated to the
  code; the real deployment path uses the official `postgres:16-alpine`
  Docker image via docker-compose, unaffected).
- Alembic's revision chain verified valid (`alembic heads` resolves `0001`
  correctly); actual `alembic upgrade head` against real Postgres should be
  run once you have the docker-compose stack up.
- Flutter side validated via brace-balance + import-consistency checks and
  a provider-wiring trace (no Flutter SDK available in this sandbox);
  widget tests written for phone entry validation, OTP failure display,
  and repository call verification using a fake `AuthRepository`.

## Open Items for Later Phases

- Rate limiting on `/otp/request` (prevent OTP-spam abuse) - flagged, not
  built; natural fit alongside Phase 17 (Cloud Deployment) infra hardening.
- Real SMS provider (MSG91/Twilio) - `get_otp_provider()`'s production
  branch currently raises `NotImplementedError` deliberately, forcing this
  decision before a real deploy rather than silently no-op-ing.
- Flutter `json_serializable`/`freezed` codegen - not needed yet given
  current model simplicity.
- Language-preference / profile UI - separate phase, not auth.

## How to Verify This Phase

Backend:
```bash
cd backend/api_gateway
pip install -r requirements.txt
export PYTHONPATH=".:.."
pytest tests/ -v
```

Full stack, once Postgres/Redis are up via docker-compose:
```bash
alembic upgrade head   # run once, from backend/api_gateway/
curl -X POST http://localhost:8000/api/v1/auth/otp/request \
  -H "Content-Type: application/json" -d '{"phone_number":"9876543210"}'
# check api_gateway container logs for the DEV OTP (DevOTPProvider logs it)
curl -X POST http://localhost:8000/api/v1/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"9876543210","otp":"<from logs>","display_name":"Priya"}'
```

Flutter: `flutter run`, enter a number, check the `api_gateway` container
logs for the OTP (dev mode logs it instead of sending real SMS).
