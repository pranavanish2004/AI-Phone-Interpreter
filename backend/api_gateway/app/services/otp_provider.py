"""
OTP delivery abstraction.

Why an interface here too, same pattern as MessageBroker (Phase 1) and the
planned STT/Translation/TTS providers: we don't have a live MSG91/Twilio
account to send real SMS in this build. Business logic (the AuthService)
depends on the ABSTRACT OTPProvider, not on any specific SMS vendor, so
swapping in a real provider later is a one-line change in the DI wiring,
not a rewrite of the auth flow.
"""

import logging
import random
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class OTPProvider(ABC):
    @abstractmethod
    async def send_otp(self, phone_number: str, otp: str) -> None:
        """Deliver the OTP to the user. Raises on delivery failure."""
        raise NotImplementedError


class DevOTPProvider(OTPProvider):
    """
    Development-mode provider: logs the OTP instead of sending a real SMS.

    NEVER use in production - gated by settings.is_production at the DI
    wiring point (see services/auth_service.py's provider selection), not
    inside this class itself, so the decision of which provider to use is
    visible in one place rather than this class silently checking
    environment flags itself.
    """

    async def send_otp(self, phone_number: str, otp: str) -> None:
        logger.info(
            "DEV OTP (not actually sent via SMS)",
            extra={"phone_number": phone_number, "otp": otp},
        )


def generate_otp(length: int = 6) -> str:
    """Generates a numeric OTP. Uses `random`, not `secrets`, deliberately:
    OTPs are short-lived, single-use, and rate-limited (rate limiting is
    noted as a later hardening item, see phase notes) - they don't need
    cryptographically secure randomness the way a session token does."""
    return "".join(random.choices("0123456789", k=length))
