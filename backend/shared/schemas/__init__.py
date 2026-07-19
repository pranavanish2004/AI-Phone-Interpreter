"""
Public API of the shared schemas package.

Every service will import from here like:
    from shared.schemas import AudioChunk, TranslationEvent, LanguageCode

instead of reaching into individual files - this gives us one place to
control what's considered a "public contract" vs internal helper.
"""

from .enums import LanguageCode, CallStatus, ProcessingStage
from .audio import AudioChunk
from .transcript import TranscriptEvent
from .translation import TranslationEvent, LanguageSegment
from .tts import SynthesizedAudioEvent
from .call_session import CallSession, Participant

__all__ = [
    "LanguageCode",
    "CallStatus",
    "ProcessingStage",
    "AudioChunk",
    "TranscriptEvent",
    "TranslationEvent",
    "LanguageSegment",
    "SynthesizedAudioEvent",
    "CallSession",
    "Participant",
]
