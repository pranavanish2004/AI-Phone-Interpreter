"""
TranslationEvent: what translation_service publishes after converting a
finalized transcript into the listener's preferred language/mode.

Why we keep both source_text and translated_text (and not just the output):
    1. Debugging/QA - when a translation looks wrong, we need to see exactly
       what was fed in, including any mixed-language segments.
    2. conversation_service needs BOTH to build context for future turns
       (Phase 11) - e.g. knowing that "meeting" stayed untranslated because
       it's an English loanword commonly used in Telugu speech.
    3. Analytics - measuring translation quality over time requires the pair.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from .enums import LanguageCode


class LanguageSegment(BaseModel):
    """
    One contiguous span of text in a single language, used to represent
    mixed-language (code-switched) input, e.g. "Bro meeting ki late avutanu"
    -> [("Bro meeting ki", en/te-mixed), ("late avutanu", te)]

    Phase 10 (Mixed Language Detection) is what actually populates this list;
    for now it's just part of the contract.
    """

    text: str
    language: LanguageCode
    start_char: int
    end_char: int


class TranslationEvent(BaseModel):
    call_id: str
    speaker_user_id: str
    listener_user_id: str
    utterance_id: str

    source_text: str = Field(..., description="Original finalized transcript")
    source_language: LanguageCode
    source_segments: list[LanguageSegment] = Field(
        default_factory=list,
        description="Populated when source_text is code-mixed; empty if the "
        "utterance was monolingual",
    )

    translated_text: str = Field(
        ..., description="Meaning-preserving translation in the listener's "
        "preferred language/mode (e.g. Hinglish, not literal Hindi)"
    )
    target_language: LanguageCode

    used_context: bool = Field(
        default=False,
        description="True if conversation_service's rolling context was "
        "injected into the translation prompt (affects pronoun resolution, "
        "topic continuity, etc.)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
