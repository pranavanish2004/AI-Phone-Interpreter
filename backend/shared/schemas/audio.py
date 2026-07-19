"""
AudioChunk: the contract for audio data flowing between audio_service and
speech_service via Redis Streams.

Why a "chunk" and not a whole utterance:
    We are doing STREAMING speech recognition (a functional requirement), not
    "record the whole sentence, then transcribe." That means audio has to be
    sliced into small time-boxed chunks (typically 20-100ms of PCM audio) and
    pushed downstream continuously, so the speech_service can start
    transcribing before the speaker has even finished talking. This is what
    makes the system feel low-latency instead of walkie-talkie-like.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AudioChunk(BaseModel):
    """A single small slice of audio belonging to one ongoing utterance."""

    call_id: str = Field(..., description="ID of the call this audio belongs to")
    speaker_user_id: str = Field(..., description="User ID of who is speaking")
    sequence_number: int = Field(
        ..., description="Monotonically increasing index within the utterance, "
        "used to reassemble/ order chunks that may arrive slightly out of order"
    )
    utterance_id: str = Field(
        ..., description="Groups chunks belonging to the same continuous "
        "utterance (from VAD 'speech start' to 'speech end')"
    )
    pcm_data_base64: str = Field(
        ..., description="Raw PCM audio bytes, base64-encoded for JSON transport "
        "over Redis Streams"
    )
    sample_rate_hz: int = Field(default=16000, description="16kHz is standard for STT models")
    channels: int = Field(default=1, description="Mono audio; stereo is unnecessary for speech")
    is_final_chunk: bool = Field(
        default=False, description="True when VAD detects end-of-speech; tells "
        "downstream services to flush/finalize processing for this utterance"
    )
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_schema_extra = {
            "example": {
                "call_id": "call_123",
                "speaker_user_id": "user_A",
                "sequence_number": 4,
                "utterance_id": "utt_789",
                "pcm_data_base64": "UklGRi...==",
                "sample_rate_hz": 16000,
                "channels": 1,
                "is_final_chunk": False,
            }
        }
