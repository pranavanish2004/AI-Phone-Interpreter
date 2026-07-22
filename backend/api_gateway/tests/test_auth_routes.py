"""
Route-level integration tests for /api/v1/auth/*.

Overrides `get_auth_service` and `get_db_session` at the FastAPI app level
so these tests exercise the REAL route -> service -> repository chain
end-to-end over HTTP, but against an in-memory SQLite DB and fake OTP
storage instead of real Postgres/Redis (see phase notes for why).
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.auth.dependencies import get_auth_service
from app.core.database import Base, get_db_session
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from tests.fakes import FakeOTPProvider, FakeOTPStore


@pytest_asyncio.fixture
async def engine():
    # StaticPool is essential here: without it, every new connection to
    # "sqlite+aiosqlite:///:memory:" gets its OWN separate, empty database.
    # This test's route calls get_db_session and get_auth_service, which
    # (in this override) open separate connections - StaticPool makes them
    # share the SAME single underlying connection/database instead of each
    # seeing an independent, empty one. This is a SQLite-specific quirk
    # that doesn't apply to Postgres (the real docker-compose target),
    # where every connection naturally points at the same database.
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def shared_otp_store() -> FakeOTPStore:
    return FakeOTPStore()


@pytest.fixture
def shared_otp_provider() -> FakeOTPProvider:
    return FakeOTPProvider()


@pytest.fixture
def client(engine, shared_otp_store, shared_otp_provider) -> TestClient:
    from typing import Annotated

    from fastapi import Depends

    from app.main import create_app

    app = create_app()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    def override_get_auth_service(
        db: Annotated["object", Depends(get_db_session)],
    ) -> AuthService:
        # Mirrors the REAL get_auth_service in dependencies.py exactly: it
        # takes `db` via Depends(get_db_session) - the ORIGINAL callable,
        # not a test-specific wrapper. This matters because FastAPI's
        # per-request dependency cache is keyed by the ORIGINALLY DECLARED
        # callable at each site, evaluated BEFORE dependency_overrides
        # substitution - not by the final resolved function. My first
        # attempt at this fixture declared `Depends(override_get_db_session)`
        # here directly, which - despite resolving to the same override
        # function as the route's own `Depends(get_db_session)` - produced
        # a DIFFERENT cache key and therefore a completely separate,
        # never-committed session. Verified via debug instrumentation:
        # two distinct session ids were created within one request until
        # this fix. Declaring `Depends(get_db_session)` here (matching the
        # route's own declaration) makes both cache keys identical, so
        # FastAPI correctly reuses the single per-request session - exactly
        # matching production behavior.
        return AuthService(UserRepository(db), shared_otp_store, shared_otp_provider)

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_auth_service] = override_get_auth_service

    return TestClient(app)


def test_request_otp_returns_204(client: TestClient, shared_otp_provider: FakeOTPProvider) -> None:
    response = client.post("/api/v1/auth/otp/request", json={"phone_number": "9876543210"})
    assert response.status_code == 204
    assert len(shared_otp_provider.sent) == 1


def test_request_otp_normalizes_phone_number(
    client: TestClient, shared_otp_provider: FakeOTPProvider
) -> None:
    # Sent without +91 prefix - should still normalize to +91XXXXXXXXXX
    client.post("/api/v1/auth/otp/request", json={"phone_number": "9876543210"})
    sent_phone, _ = shared_otp_provider.sent[0]
    assert sent_phone == "+919876543210"


def test_request_otp_rejects_invalid_phone_number(client: TestClient) -> None:
    response = client.post("/api/v1/auth/otp/request", json={"phone_number": "12345"})
    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_VALIDATION_ERROR"


def test_full_register_and_login_flow(client: TestClient, shared_otp_provider: FakeOTPProvider) -> None:
    # Step 1: request OTP
    client.post("/api/v1/auth/otp/request", json={"phone_number": "9876543210"})
    _, otp = shared_otp_provider.sent[0]

    # Step 2: verify OTP as a new user
    verify_response = client.post(
        "/api/v1/auth/otp/verify",
        json={"phone_number": "9876543210", "otp": otp, "display_name": "Priya"},
    )
    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["user"]["display_name"] == "Priya"
    assert body["user"]["phone_number"] == "+919876543210"
    token = body["access_token"]
    assert token

    # Step 3: use the token on a protected route
    me_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["display_name"] == "Priya"


def test_protected_route_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_protected_route_rejects_garbage_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
