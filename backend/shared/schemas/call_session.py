"""
CallSession: represents the live state of an ongoing call. This is what gets
stored in Redis (fast, ephemeral) while the call is active, and mirrored into
PostgreSQL's `calls` table for durable history once the call ends (Phase 5+).
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from .enums import CallStatus, LanguageCode


class Participant(BaseModel):
    user_id: str
    preferred_language: LanguageCode = Field(
        ..., description="What THIS user wants to hear other people in - "
        "e.g. User A speaks Telugu but has preferred_language=hi if they "
        "want everything translated to Hindi for them"
    )
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CallSession(BaseModel):
    call_id: str
    status: CallStatus = CallStatus.INITIATED
    participants: list[Participant] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    def get_listener_language(self, speaker_user_id: str) -> LanguageCode | None:
        """
        Given who is speaking, find the OTHER participant's preferred
        language - i.e. what we need to translate INTO.

        This is intentionally simple (2-party calls only) for the MVP.
        Multi-party calls would need this to return a list instead - noted
        here as a known future extension point, not solved now (YAGNI).
        """
        others = [p for p in self.participants if p.user_id != speaker_user_id]
        return others[0].preferred_language if others else None
