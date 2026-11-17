"""Text-to-speech providers (tried in order by `ChainTTS`).

* AzureTTS      - Azure Speech neural voices over REST, official (free F0 tier:
  0.5M characters/month). Needs AZURE_SPEECH_KEY.
* EdgeTTS       - the same Microsoft neural voices through the free "Read aloud"
  service used by the Edge browser (python package `edge-tts`). No key, no
  account. Unofficial: Microsoft could change or block it, hence the fallbacks.
* GoogleFreeTTS - the voice behind Google Translate's speaker button. No key.
  Unofficial; lower quality; max ~200 characters per request (handled here).
* ElevenLabsTTS - optional. Free plan is ~10 min/month; Telugu needs model eleven_v3.
* BrowserTTS    - no audio from the server: the listening device speaks the text
  with its own `speechSynthesis` voice. Always the last resort.
* MockTTS       - short generated WAV tone, for tests.

Default order (TTS_PROVIDER=auto): azure (if key) -> edge (if installed) -> google -> browser.
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
import struct
import time
import wave
from dataclasses import dataclass
from xml.sax.saxutils import escape

from .config import LANGUAGES, Settings
from .http_util import ProviderError, request, short

log = logging.getLogger("interpreter.tts")


@dataclass
class TTSResult:
    audio: bytes | None          # None -> device must speak the text itself
    mime: str = ""
    provider: str = "browser"


class TTS:
    name = "base"

    async def synthesize(self, text: str, lang: str) -> TTSResult:  # pragma: no cover
        raise NotImplementedError

    def supports(self, lang: str) -> bool:
        return True


class BrowserTTS(TTS):
    name = "browser"

    async def synthesize(self, text: str, lang: str) -> TTSResult:
        return TTSResult(audio=None, provider=self.name)


def tone_wav(duration_s: float = 0.25, freq: float = 660.0, rate: int = 16000) -> bytes:
    n = int(duration_s * rate)
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


class MockTTS(TTS):
    name = "mock"

    async def synthesize(self, text: str, lang: str) -> TTSResult:
        return TTSResult(audio=tone_wav(0.2 + min(len(text), 40) * 0.01), mime="audio/wav", provider=self.name)


class AzureTTS(TTS):
    name = "azure"
    OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

    def __init__(self, settings: Settings):
        self.key = settings.azure_speech_key
        self.region = settings.azure_speech_region
        self.endpoint = settings.azure_speech_endpoint_tts or (
            f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1")
        self.settings = settings
        self.timeout = settings.provider_timeout_s

    def ssml(self, text: str, lang: str) -> str:
        voice = self.settings.voice_for(lang)
        locale = "-".join(voice.split("-")[:2])
        return (f"<speak version='1.0' xml:lang='{locale}'>"
                f"<voice xml:lang='{locale}' name='{voice}'>{escape(text)}</voice></speak>")

    async def synthesize(self, text: str, lang: str, output_format: str | None = None) -> TTSResult:
        if not self.key:
            raise ProviderError(self.name, "AZURE_SPEECH_KEY is not set")
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": output_format or self.OUTPUT_FORMAT,
            "User-Agent": "ai-phone-interpreter",
        }
        resp = await request("POST", self.endpoint, provider=self.name, headers=headers,
                             data=self.ssml(text, lang).encode("utf-8"), timeout=self.timeout)
        if resp.status != 200 or not resp.body:
            hint = " | Check AZURE_SPEECH_KEY / AZURE_SPEECH_REGION." if resp.status == 401 else ""
            raise ProviderError(self.name, f"HTTP {resp.status}: {short(resp.text())}{hint}", resp.status)
        mime = "audio/wav" if (output_format or "").startswith("riff") else "audio/mpeg"
        return TTSResult(audio=resp.body, mime=mime, provider=self.name)


class EdgeTTS(TTS):
    """Microsoft Edge "Read aloud" neural voices via the `edge-tts` package (no key)."""

    name = "edge"

    def __init__(self, settings: Settings, module=None):
        self.settings = settings
        self.timeout = settings.provider_timeout_s
        self._module = module

    @staticmethod
    def available() -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def _mod(self):
        if self._module is None:
            try:
                import edge_tts
            except ImportError:
                raise ProviderError(self.name, "package edge-tts is not installed (pip install edge-tts)") from None
            self._module = edge_tts
        return self._module

    async def _collect(self, text: str, voice: str) -> bytes:
        comm = self._mod().Communicate(text=text, voice=voice)
        audio = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                audio.extend(chunk["data"])
        return bytes(audio)

    async def synthesize(self, text: str, lang: str) -> TTSResult:
        voice = self.settings.voice_for(lang)
        try:
            audio = await asyncio.wait_for(self._collect(text, voice), self.timeout)
        except ProviderError:
            raise
        except asyncio.TimeoutError:
            raise ProviderError(self.name, f"timed out after {self.timeout}s") from None
        except Exception as e:
            raise ProviderError(self.name, f"{type(e).__name__}: {e}") from None
        if not audio:
            raise ProviderError(self.name, "no audio received")
        return TTSResult(audio=audio, mime="audio/mpeg", provider=self.name)


def _split_for_google(text: str, limit: int = 190) -> list[str]:
    words, parts, cur = text.split(), [], ""
    for w in words:
        while len(w) > limit:            # a single giant "word"
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(w[:limit])
            w = w[limit:]
        if cur and len(cur) + 1 + len(w) > limit:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        parts.append(cur)
    return parts


class GoogleFreeTTS(TTS):
    """The voice behind Google Translate's speaker button (no key, unofficial)."""

    name = "google"

    def __init__(self, settings: Settings):
        self.endpoint = settings.google_tts_endpoint
        self.timeout = settings.provider_timeout_s

    async def synthesize(self, text: str, lang: str) -> TTSResult:
        pieces = _split_for_google(text) or [text]
        audio = bytearray()
        for idx, piece in enumerate(pieces):
            params = {"ie": "UTF-8", "client": "tw-ob", "tl": LANGUAGES[lang]["translator"], "q": piece,
                      "total": str(len(pieces)), "idx": str(idx), "textlen": str(len(piece)), "ttsspeed": "1"}
            resp = await request("GET", self.endpoint, provider=self.name, params=params, timeout=self.timeout,
                                 headers={"User-Agent": "Mozilla/5.0", "Referer": "https://translate.google.com/"})
            ctype = str(resp.headers.get("Content-Type", resp.headers.get("content-type", "")))
            looks_mp3 = resp.body.startswith((b"ID3", b"\xff\xf3", b"\xff\xfb", b"\xff\xf2"))
            if resp.status != 200 or not resp.body or ("audio" not in ctype and not looks_mp3):
                raise ProviderError(self.name, f"HTTP {resp.status} {ctype}: {short(resp.text()[:200])}", resp.status)
            audio.extend(resp.body)
        return TTSResult(audio=bytes(audio), mime="audio/mpeg", provider=self.name)


class ElevenLabsTTS(TTS):
    """Optional. Use a *premade* voice id (library/community voices need a paid plan for API use)."""

    name = "elevenlabs"

    def __init__(self, settings: Settings):
        self.key = settings.elevenlabs_api_key
        self.default_voice = settings.elevenlabs_voice
        self.voices = {"en": settings.elevenlabs_voice_en}
        self.model = settings.elevenlabs_model
        self.timeout = settings.provider_timeout_s

    def voice_for(self, lang: str) -> str:
        return self.voices.get(lang) or self.default_voice

    def supports(self, lang: str) -> bool:
        if not (self.key and self.voice_for(lang)):
            return False
        # Telugu is only supported by eleven_v3 (multilingual_v2 / flash do Hindi + Tamil, not Telugu)
        return lang != "te" or self.model.startswith("eleven_v3")

    async def synthesize(self, text: str, lang: str) -> TTSResult:
        import json
        voice = self.voice_for(lang)
        if not (self.key and voice):
            raise ProviderError(self.name, f"no ElevenLabs voice configured for {lang}")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_22050_32"
        headers = {"xi-api-key": self.key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
        body = json.dumps({"text": text, "model_id": self.model, "language_code": lang}).encode()
        resp = await request("POST", url, provider=self.name, headers=headers, data=body, timeout=self.timeout)
        if resp.status != 200:
            raise ProviderError(self.name, f"HTTP {resp.status}: {short(resp.text())}", resp.status)
        return TTSResult(audio=resp.body, mime="audio/mpeg", provider=self.name)


class ChainTTS(TTS):
    name = "chain"
    COOLDOWN_AUTH_S = 300.0     # bad key / no credits / blocked
    COOLDOWN_OTHER_S = 30.0     # network hiccup, timeout, unexpected response

    def __init__(self, providers: list[TTS]):
        self.providers = providers
        self._disabled_until: dict[str, float] = {}
        self.last_errors: list[str] = []

    async def synthesize(self, text: str, lang: str) -> TTSResult:
        errors: list[str] = []
        now = time.monotonic()
        for p in self.providers:
            if not p.supports(lang) or self._disabled_until.get(p.name, 0) > now:
                continue
            try:
                res = await p.synthesize(text, lang)
                self.last_errors = errors
                return res
            except ProviderError as e:
                errors.append(str(e))
                log.warning("TTS provider failed: %s", e)
                auth = e.status in (401, 402, 403, 429) or "not set" in e.message or "not installed" in e.message
                self._disabled_until[p.name] = time.monotonic() + (self.COOLDOWN_AUTH_S if auth else self.COOLDOWN_OTHER_S)
            except Exception as e:
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                log.warning("TTS provider crashed: %s", e)
                self._disabled_until[p.name] = time.monotonic() + self.COOLDOWN_OTHER_S
        self.last_errors = errors
        # Last resort: let the listening device speak it.
        return TTSResult(audio=None, provider="browser")


TTS_NAMES = ("azure", "edge", "google", "elevenlabs", "browser", "mock")


def build_tts(settings: Settings) -> ChainTTS:
    choice = settings.tts_provider
    if choice == "auto":
        names = (["azure"] if settings.azure_speech_configured else []) + \
                (["edge"] if EdgeTTS.available() else []) + ["google", "browser"]
    else:
        names = [n.strip() for n in choice.split(",") if n.strip()]
    unknown = [n for n in names if n not in TTS_NAMES]
    if unknown:
        raise ValueError(f"unknown TTS_PROVIDER(s): {unknown}; choose from {list(TTS_NAMES)}")
    makers = {
        "azure": lambda: AzureTTS(settings),
        "edge": lambda: EdgeTTS(settings),
        "google": lambda: GoogleFreeTTS(settings),
        "elevenlabs": lambda: ElevenLabsTTS(settings),
        "browser": lambda: BrowserTTS(),
        "mock": lambda: MockTTS(),
    }
    providers: list[TTS] = [makers[n]() for n in names]
    if not any(isinstance(p, BrowserTTS) for p in providers):
        providers.append(BrowserTTS())
    return ChainTTS(providers)


__all__ = ["TTSResult", "build_tts", "AzureTTS", "EdgeTTS", "GoogleFreeTTS", "MockTTS", "BrowserTTS",
           "ElevenLabsTTS", "ChainTTS", "LANGUAGES"]
