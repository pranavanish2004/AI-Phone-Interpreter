"""
AuthService: orchestrates OTP request/verification, user creation, and
token issuance. This is the layer routes call into - routes stay thin
(parse request, call service, return response), all decision logic lives
here where it's independently testable without spinning up FastAPI.
"""

from app.core.exceptions import ValidationError
from app.core.security import create_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.otp_provider import OTPProvider, generate_otp
from app.services.otp_store import OTPStore


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        otp_store: OTPStore,
        otp_provider: OTPProvider,
    ):
        self._users = user_repository
        self._otp_store = otp_store
        self._otp_provider = otp_provider

    async def request_otp(self, phone_number: str) -> None:
        otp = generate_otp()
        await self._otp_store.save(phone_number, otp)
        await self._otp_provider.send_otp(phone_number, otp)

    async def verify_otp_and_authenticate(
        self, phone_number: str, otp: str, display_name: str | None
    ) -> tuple[User, str]:
        """
        Returns (user, access_token).

        Handles BOTH first-time registration and returning-user login
        through the same endpoint - deliberately, so the Flutter client
        doesn't need to know in advance whether a phone number is new
        (avoiding a phone-number-enumeration side channel where a
        "does this account exist" check could be probed separately).
        """
        is_valid = await self._otp_store.verify_and_consume(phone_number, otp)
        if not is_valid:
            raise ValidationError("Invalid or expired OTP.")

        user = await self._users.get_by_phone_number(phone_number)
        if user is None:
            if not display_name:
                raise ValidationError(
                    "display_name is required when registering a new account."
                )
            user = User(
                phone_number=phone_number,
                display_name=display_name,
                preferred_language="en",
            )
            await self._users.add(user)

        token = create_access_token(user_id=str(user.id))
        return user, token
