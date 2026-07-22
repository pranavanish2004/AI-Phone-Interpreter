"""
JWT-based auth: token creation, decoding, and the `get_current_user`
dependency that protects routes.

Why JWT (not server-side sessions):
    api_gateway is meant to run as multiple stateless replicas behind a load
    balancer (a functional requirement: low latency under load via
    horizontal scaling). A JWT carries its own validity proof (the
    signature), so any replica can authenticate a request without a shared
    session store lookup. The tradeoff - can't instantly revoke a token
    before it expires - is acceptable given the short expiry
    (jwt_access_token_expire_minutes, default 60) configured in Phase 3.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

settings = get_settings()

_bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str  # user_id
    exp: datetime


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**raw)
    except jwt.ExpiredSignatureError as e:
        raise UnauthorizedError("Session expired. Please log in again.") from e
    except jwt.InvalidTokenError as e:
        raise UnauthorizedError("Invalid authentication token.") from e


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """
    FastAPI dependency protecting authenticated routes.

    Usage:
        @router.get("/me")
        async def me(user_id: str = Depends(get_current_user_id)): ...

    Returns just the user_id (a string) rather than a full User object
    deliberately - fetching the FULL user record is a separate concern
    (some routes need it, some just need to know "who is this request
    from" for authorization checks) and belongs to whichever route handler
    actually needs it, via the repository - not baked into every
    authenticated route whether it needs a DB round-trip or not.
    """
    if credentials is None:
        raise UnauthorizedError("Missing authentication token.")
    payload = decode_access_token(credentials.credentials)
    return payload.sub
