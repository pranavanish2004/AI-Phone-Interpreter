"""
Unit tests for AuthService - the business logic layer.

Uses a REAL UserRepository against an in-memory SQLite database (not
Postgres - see phase notes for why) so these tests exercise real
SQLAlchemy query behavior, but FAKE OTPStore/OTPProvider (see fakes.py)
since OTP delivery/storage is an external-ish concern already covered by
the interface abstraction.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.exceptions import ValidationError
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from tests.fakes import FakeOTPProvider, FakeOTPStore


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def otp_store() -> FakeOTPStore:
    return FakeOTPStore()


@pytest.fixture
def otp_provider() -> FakeOTPProvider:
    return FakeOTPProvider()


@pytest.fixture
def auth_service(db_session, otp_store, otp_provider) -> AuthService:
    return AuthService(UserRepository(db_session), otp_store, otp_provider)


@pytest.mark.asyncio
async def test_request_otp_saves_and_sends(
    auth_service: AuthService, otp_store: FakeOTPStore, otp_provider: FakeOTPProvider
) -> None:
    await auth_service.request_otp("+919876543210")

    assert len(otp_provider.sent) == 1
    sent_phone, sent_otp = otp_provider.sent[0]
    assert sent_phone == "+919876543210"
    # The OTP that was "sent" must be exactly what's retrievable/verifiable
    assert await otp_store.verify_and_consume("+919876543210", sent_otp) is True


@pytest.mark.asyncio
async def test_verify_otp_registers_new_user(auth_service: AuthService, otp_store: FakeOTPStore) -> None:
    await otp_store.save("+919876543210", "111111")

    user, token = await auth_service.verify_otp_and_authenticate(
        "+919876543210", "111111", display_name="Priya"
    )

    assert user.phone_number == "+919876543210"
    assert user.display_name == "Priya"
    assert token  # a non-empty JWT was issued


@pytest.mark.asyncio
async def test_verify_otp_rejects_wrong_code(auth_service: AuthService, otp_store: FakeOTPStore) -> None:
    await otp_store.save("+919876543210", "111111")

    with pytest.raises(ValidationError):
        await auth_service.verify_otp_and_authenticate(
            "+919876543210", "000000", display_name="Priya"
        )


@pytest.mark.asyncio
async def test_verify_otp_requires_display_name_for_new_user(
    auth_service: AuthService, otp_store: FakeOTPStore
) -> None:
    await otp_store.save("+919876543210", "111111")

    with pytest.raises(ValidationError):
        await auth_service.verify_otp_and_authenticate(
            "+919876543210", "111111", display_name=None
        )


@pytest.mark.asyncio
async def test_verify_otp_logs_in_existing_user_without_display_name(
    auth_service: AuthService, otp_store: FakeOTPStore
) -> None:
    # First: register
    await otp_store.save("+919876543210", "111111")
    first_user, _ = await auth_service.verify_otp_and_authenticate(
        "+919876543210", "111111", display_name="Priya"
    )

    # Second: log in again, no display_name needed, same user returned
    await otp_store.save("+919876543210", "222222")
    second_user, _ = await auth_service.verify_otp_and_authenticate(
        "+919876543210", "222222", display_name=None
    )

    assert first_user.id == second_user.id


@pytest.mark.asyncio
async def test_otp_is_single_use(auth_service: AuthService, otp_store: FakeOTPStore) -> None:
    await otp_store.save("+919876543210", "111111")
    await auth_service.verify_otp_and_authenticate("+919876543210", "111111", display_name="Priya")

    # Replaying the same OTP must fail - it was consumed by the first call.
    with pytest.raises(ValidationError):
        await auth_service.verify_otp_and_authenticate(
            "+919876543210", "111111", display_name="Priya"
        )
