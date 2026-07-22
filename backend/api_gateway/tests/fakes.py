"""
Test doubles for the auth feature's external-ish dependencies (OTP storage,
OTP delivery). Using simple in-memory fakes rather than mocking library
internals keeps these tests fast, and testing AGAINST THE INTERFACE
(OTPProvider) rather than a concrete class means these fakes are exactly as
valid a substitute as a real Redis-backed store or real SMS vendor would
be - this is the payoff of the interface-based design from Phase 1 onward.
"""

from app.services.otp_provider import OTPProvider


class FakeOTPStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def save(self, phone_number: str, otp: str) -> None:
        self._store[phone_number] = otp

    async def verify_and_consume(self, phone_number: str, otp: str) -> bool:
        stored = self._store.get(phone_number)
        if stored is None or stored != otp:
            return False
        del self._store[phone_number]
        return True


class FakeOTPProvider(OTPProvider):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_otp(self, phone_number: str, otp: str) -> None:
        self.sent.append((phone_number, otp))
