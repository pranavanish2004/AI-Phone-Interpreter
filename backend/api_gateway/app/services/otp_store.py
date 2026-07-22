"""
Short-lived OTP storage in Redis.

Why NOT reuse the MessageBroker (Redis Streams) abstraction here:
    MessageBroker models an append-only event log for inter-service
    streaming (Phase 1). An OTP is fundamentally different: a single
    key-value pair with a TTL and no history/replay/consumer-group
    semantics. Forcing this through the streaming abstraction would be
    using the wrong tool. This talks to Redis directly via simple
    GET/SET/DELETE with expiry - a deliberate, narrow exception, same as
    `check_redis_connection`'s direct client access in core/redis.py.
"""

import redis.asyncio as redis

_OTP_KEY_PREFIX = "otp:"
_OTP_TTL_SECONDS = 300  # 5 minutes - long enough for a real SMS to arrive
                        # and be typed, short enough to limit brute-force
                        # exposure window


class OTPStore:
    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url, decode_responses=True)

    async def save(self, phone_number: str, otp: str) -> None:
        await self._client.set(f"{_OTP_KEY_PREFIX}{phone_number}", otp, ex=_OTP_TTL_SECONDS)

    async def verify_and_consume(self, phone_number: str, otp: str) -> bool:
        """
        Checks the OTP and, if correct, DELETES it immediately - an OTP is
        single-use. Without consuming it, a leaked/observed OTP could be
        replayed to log in again within the 5-minute TTL window.
        """
        key = f"{_OTP_KEY_PREFIX}{phone_number}"
        stored = await self._client.get(key)
        if stored is None or stored != otp:
            return False
        await self._client.delete(key)
        return True
