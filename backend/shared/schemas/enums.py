"""
Shared enumerations used across every microservice.

Why this file exists:
    Every service (speech, language, translation, tts, conversation) needs to
    agree on the exact same set of language codes and status values. If each
    service defined its own strings ("telugu" vs "te" vs "TE"), we would get
    silent bugs where one service's output doesn't match another's expected
    input. Enums give us a single source of truth, and Pydantic will reject
    any value that isn't one of these — so a typo becomes a loud validation
    error instead of a silent mismatch.
"""

from enum import Enum


class LanguageCode(str, Enum):
    """
    Supported languages/language-modes for the interpreter.

    Note that Tenglish and Hinglish are NOT translation targets on their own
    right the way Telugu/Hindi/English are — they are *input modes*
    (code-mixed speech). We still give them explicit codes because the
    language_service needs to report "this utterance was Tenglish" as a
    distinct detection result from "this utterance was pure Telugu": that
    distinction changes how the translation_service prompts its model
    (see Phase 12).
    """

    TELUGU = "te"
    HINDI = "hi"
    ENGLISH = "en"
    TENGLISH = "te-en"   # Telugu + English code-mixed
    HINGLISH = "hi-en"   # Hindi + English code-mixed


class CallStatus(str, Enum):
    """Lifecycle states of a call, stored in Postgres and broadcast over WS."""

    INITIATED = "initiated"
    RINGING = "ringing"
    CONNECTED = "connected"
    ENDED = "ended"
    FAILED = "failed"


class ProcessingStage(str, Enum):
    """
    Which stage of the pipeline an event came from. Used for tracing/logging
    so we can measure per-stage latency (critical for a low-latency system).
    """

    AUDIO_CAPTURED = "audio_captured"
    AUDIO_CLEANED = "audio_cleaned"          # after noise reduction/echo cancel
    VOICE_DETECTED = "voice_detected"        # VAD said "speech present"
    TRANSCRIBED = "transcribed"              # STT output
    LANGUAGE_DETECTED = "language_detected"
    TRANSLATED = "translated"
    SYNTHESIZED = "synthesized"              # TTS output ready
