"""
SynthesizedAudioEvent: what tts_service publishes after converting translated
text into speech audio, ready to be piped back into the WebRTC stream toward
the listener.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from .enums import LanguageCode


class SynthesizedAudioEvent(BaseModel):
    call_id: str
    listener_user_id: str
    utterance_id: str

    audio_chunk_base64: str = Field(
        ..., description="Synthesized speech audio (PCM or Opus, base64-encoded)"
    )
    sequence_number: int = Field(
        ..., description="Ordering index - TTS is also streamed chunk-by-chunk "
        "rather than waiting for the full sentence to be synthesized, to keep "
        "latency down"
    )
    is_final_chunk: bool = Field(default=False)

    language: LanguageCode
    voice_id: str = Field(
        ..., description="Which TTS voice profile was used - lets us keep a "
        "consistent, natural-sounding voice per target language"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
