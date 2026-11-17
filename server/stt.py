"""Server-side speech-to-text.

Two ways to get text in this app:

1. "browser"  - the device's own browser does recognition (Chrome / Edge Web
   Speech API, free, supports te-IN and en-IN) and sends us text.
   Nothing to do on the server, so there is no class for it here.
2. "azure"    - the device streams 16 kHz PCM to the server, `vad.py` cuts it
   into utterances, and `AzureSTT` sends each utterance to Azure Speech's REST
   short-audio endpoint (free F0 tier: 5 audio hours/month).

`MockSTT` is for tests.
"""
from __future__ import annotations

import io
import json
import logging
import wave

from .config import LANGUAGES, Settings
from .http_util import ProviderError, request, short

log = logging.getLogger("interpreter.stt")

SAMPLE_RATE = 16000


def pcm16_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_to_pcm16(wav_bytes: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("expected mono 16-bit WAV")
        return w.readframes(w.getnframes()), w.getframerate()


class STT:
    name = "base"

    async def transcribe(self, pcm16: bytes, lang: str) -> str:  # pragma: no cover
        raise NotImplementedError


class MockSTT(STT):
    """Returns a canned sentence per language (used by tests and demo-without-keys)."""

    name = "mock"
    CANNED = {"te": "నమస్కారం", "en": "hello"}

    async def transcribe(self, pcm16: bytes, lang: str) -> str:
        return self.CANNED.get(lang, "test")


class AzureSTT(STT):
    name = "azure"

    def __init__(self, settings: Settings):
        self.key = settings.azure_speech_key
        self.region = settings.azure_speech_region
        self.endpoint = settings.azure_speech_endpoint_stt or (
            f"https://{self.region}.stt.speech.microsoft.com"
            "/speech/recognition/conversation/cognitiveservices/v1")
        self.timeout = settings.provider_timeout_s

    async def transcribe(self, pcm16: bytes, lang: str) -> str:
        if not self.key:
            raise ProviderError(self.name, "AZURE_SPEECH_KEY is not set")
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        }
        params = {"language": LANGUAGES[lang]["bcp47"], "format": "simple", "profanity": "raw"}
        resp = await request("POST", self.endpoint, provider=self.name, headers=headers,
                             data=pcm16_to_wav(pcm16), params=params, timeout=self.timeout)
        if resp.status != 200:
            hint = ""
            if resp.status == 401:
                hint = (" | Check AZURE_SPEECH_KEY and that AZURE_SPEECH_REGION equals the Speech "
                        "resource's Location (e.g. centralindia).")
            raise ProviderError(self.name, f"HTTP {resp.status}: {short(resp.text())}{hint}", resp.status)
        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise ProviderError(self.name, f"non-JSON response: {short(resp.text())}") from None
        status = data.get("RecognitionStatus")
        if status == "Success":
            return (data.get("DisplayText") or "").strip()
        if status in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout"):
            return ""
        raise ProviderError(self.name, f"recognition status {status}")


def build_server_stt(settings: Settings) -> STT | None:
    """STT used for streamed audio. None means: server-side STT unavailable."""
    choice = settings.stt_provider
    if choice == "mock":
        return MockSTT()
    if choice in ("azure", "auto") and settings.azure_speech_configured:
        return AzureSTT(settings)
    return None


def default_client_mode(settings: Settings) -> str:
    """Which recognition mode the browser should start in."""
    if settings.stt_provider == "browser":
        return "browser"
    if settings.stt_provider in ("azure", "mock"):
        return "server"
    # auto: browser recognition is free, unlimited and gives live partial
    # transcripts; the page falls back to server mode if the browser lacks it.
    return "browser"
