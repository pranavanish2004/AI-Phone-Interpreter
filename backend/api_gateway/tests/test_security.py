"""Unit tests for app/core/security.py's JWT functions."""

import time

import jwt
import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token, decode_access_token


def test_create_and_decode_roundtrip() -> None:
    token = create_access_token(user_id="user-123")
    payload = decode_access_token(token)
    assert payload.sub == "user-123"


def test_decode_rejects_tampered_token() -> None:
    token = create_access_token(user_id="user-123")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(UnauthorizedError):
        decode_access_token(tampered)


def test_decode_rejects_expired_token() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    # Build an already-expired token directly (rather than sleeping past
    # the real expiry, which would make this test slow) to prove the
    # expiry check itself works.
    expired_payload = {"sub": "user-123", "exp": int(time.time()) - 10}
    expired_token = jwt.encode(
        expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(expired_token)


def test_decode_rejects_wrong_signature() -> None:
    token = jwt.encode({"sub": "user-123", "exp": int(time.time()) + 3600}, "wrong-secret-key-here-long-enough", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)
