"""
Dependency-injection wiring for the auth feature.

Why a dedicated `dependencies.py` per feature rather than constructing
services inline in route handlers: as more routes need AuthService (or as
AuthService gains more dependencies), every route would need to repeat the
same construction logic. Centralizing it here means routes just declare
`Depends(get_auth_service)` and never see the wiring details.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.otp_provider import DevOTPProvider, OTPProvider
from app.services.otp_store import OTPStore

settings = get_settings()

# Single shared OTPStore instance (holds its own Redis connection pool) -
# same rationale as the module-level `_broker` in core/redis.py: Redis
# clients are cheap to share and expensive to recreate per-request.
_otp_store = OTPStore(redis_url=str(settings.redis_url))


def get_otp_provider() -> OTPProvider:
    """
    Provider selection point: this is the ONE place that decides which
    OTPProvider implementation is active. Swapping to a real SMS vendor
    later (MSG91/Twilio) means adding e.g. `Msg91OTPProvider` and changing
    the branch below - AuthService and routes never change.
    """
    if settings.is_production:
        raise NotImplementedError(
            "A real OTP provider (e.g. MSG91/Twilio) must be configured "
            "before running in production - DevOTPProvider logs OTPs "
            "instead of sending real SMS and must never be used live."
        )
    return DevOTPProvider()


def get_auth_service(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    otp_provider: Annotated[OTPProvider, Depends(get_otp_provider)],
) -> AuthService:
    user_repository = UserRepository(db)
    return AuthService(user_repository, _otp_store, otp_provider)
