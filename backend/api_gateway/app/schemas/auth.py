"""
Request/response schemas for the auth flow.

Why separate from the SQLAlchemy `User` model (models/user.py):
Returning ORM models directly from routes leaks internal DB fields
(password_hash!) into API responses, and couples the API's public shape to
the DB schema - a DB column rename would break the client. These schemas
are the DELIBERATE public contract, independent of storage.
"""

import re
import uuid

from pydantic import BaseModel, Field, field_validator

# India mobile numbers: optionally prefixed with country code (+91 or 91),
# followed by a 10-digit number starting 6-9 (per India's numbering plan -
# numbers starting 0-5 are not valid mobile prefixes).
_INDIA_PHONE_PATTERN = re.compile(r"^(?:\+91|91)?[6-9]\d{9}$")


def _normalize_india_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not re.match(r"^[6-9]\d{9}$", digits):
        raise ValueError("Must be a valid 10-digit India mobile number")
    return f"+91{digits}"


class OTPRequestSchema(BaseModel):
    phone_number: str = Field(..., examples=["+919876543210"])

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _normalize_india_phone(v)


class OTPVerifySchema(BaseModel):
    phone_number: str
    otp: str = Field(..., min_length=4, max_length=6)
    # Only required the FIRST time a phone number verifies (i.e. new user
    # registration). Existing users verifying to log in don't need to
    # resend this - the service layer decides based on whether the user
    # already exists.
    display_name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _normalize_india_phone(v)


class UserResponseSchema(BaseModel):
    id: uuid.UUID
    phone_number: str
    display_name: str
    preferred_language: str
    is_active: bool

    model_config = {"from_attributes": True}  # lets us build this directly from an ORM User


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserResponseSchema
