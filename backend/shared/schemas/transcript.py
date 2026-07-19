"""
TranscriptEvent: what speech_service publishes after converting audio to text.

Why is_partial matters:
    Streaming STT engines emit two kinds of results:
      1. Partial/interim results - fast, low-confidence, can still change as
         more audio arrives ("I think you said... 'meeting ki lat...'")
      2. Final results - stable, won't change, safe to translate.
    We want to show partial transcripts in the UI immediately (for
    responsiveness / "the app is listening" feedback), but we only want to
    trigger translation on FINAL transcripts, otherwise we'd translate the
    same sentence multiple times as it's being refined, wasting API calls and
    producing flickering translations.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from .enums import LanguageCode


class TranscriptEvent(BaseModel):
    call_id: str
    speaker_user_id: str
    utterance_id: str
    text: str = Field(..., description="The transcribed text as recognized so far")
    is_partial: bool = Field(
        ..., description="True = interim/unstable result, False = finalized result"
    )
    detected_language_hint: LanguageCode | None = Field(
        default=None,
        description="Best-effort language guess from the STT engine itself "
        "(many STT APIs return this for free). This is a HINT only - the "
        "authoritative detection comes from language_service in Phase 9.",
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="STT engine's own confidence score, if provided"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
