"""
Auth routes: request OTP, verify OTP (login/register), get current user.

Routes stay deliberately thin - parse/validate request (Pydantic does this
automatically), call the service layer, shape the response. All decisions
(is this a new user? is the OTP valid?) live in AuthService, where they're
unit-testable without an HTTP layer at all.
"""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth.dependencies import get_auth_service
from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import get_current_user_id
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    OTPRequestSchema,
    OTPVerifySchema,
    TokenResponseSchema,
    UserResponseSchema,
)
from app.services.auth_service import AuthService
from app.core.exceptions import NotFoundError

router = APIRouter()
settings = get_settings()


@router.post("/otp/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_otp(
    payload: OTPRequestSchema,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """
    Always returns 204 regardless of whether the phone number is already
    registered - deliberately, to avoid leaking "this number exists/doesn't
    exist" via response differences (a common account-enumeration issue in
    OTP-based auth flows).
    """
    await auth_service.request_otp(payload.phone_number)


@router.post("/otp/verify", response_model=TokenResponseSchema)
async def verify_otp(
    payload: OTPVerifySchema,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponseSchema:
    user, token = await auth_service.verify_otp_and_authenticate(
        payload.phone_number, payload.otp, payload.display_name
    )
    await db.commit()  # commits the new-user insert (if any) - the route,
    # not the service, owns the transaction boundary, since routes
    # correspond 1:1 with a single logical unit of work

    return TokenResponseSchema(
        access_token=token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
        user=UserResponseSchema.model_validate(user),
    )


@router.get("/me", response_model=UserResponseSchema)
async def get_me(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponseSchema:
    """First protected route - proves the get_current_user_id dependency
    (JWT verification) actually gates access end-to-end."""
    repo = UserRepository(db)
    user: User | None = await repo.get_by_id(uuid.UUID(user_id))
    if user is None:
        raise NotFoundError("User not found.")
    return UserResponseSchema.model_validate(user)
