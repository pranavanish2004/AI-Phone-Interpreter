"""Configuration loaded from environment variables and an optional `.env` file.

No third-party dependency: the `.env` parser below handles the usual
`KEY=value`, quotes and `# comments`. Real environment variables always win
over values in `.env`.

Secrets (API keys) are only ever exposed through `Settings.public_view()`
as "configured: yes/no" - never the value itself.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value and value[0] in "\"'" and value[-1:] == value[0] and len(value) >= 2:
            value = value[1:-1]
        elif value.startswith("#"):
            value = ""          # KEY=      # comment   -> empty
        else:
            # strip inline comment:  KEY=value   # comment
            hash_pos = value.find(" #")
            if hash_pos != -1:
                value = value[:hash_pos].rstrip()
        values[key] = value
    return values


# Language table. Keys are the short codes used everywhere in the app.
#   bcp47       - speech-recognition locale (Chrome Web Speech + Azure STT)
#   translator  - code for Azure Translator / Google / MyMemory
#   azure_voice - neural voice name (Azure Speech AND Edge TTS use the same names)
LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English", "bcp47": "en-IN", "translator": "en",
           "azure_voice": "en-IN-NeerjaNeural"},
    "te": {"name": "Telugu", "native": "తెలుగు", "bcp47": "te-IN", "translator": "te",
           "azure_voice": "te-IN-ShrutiNeural"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "bcp47": "ta-IN", "translator": "ta",
           "azure_voice": "ta-IN-PallaviNeural"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "bcp47": "hi-IN", "translator": "hi",
           "azure_voice": "hi-IN-SwaraNeural"},
}

# Default language for each seat; every user can pick another one when joining.
ROLE_LANG = {"laptop": "en", "phone": "te"}


@dataclass
class Settings:
    # providers: "auto" picks the best configured one
    stt_provider: str = "auto"          # auto | azure | browser | mock
    translate_provider: str = "auto"    # auto | azure | google_free | mymemory | mock  (or comma list)
    tts_provider: str = "auto"          # auto | azure | edge | google | elevenlabs | browser | mock  (or comma list)

    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_endpoint_stt: str = ""   # optional override (tests / private endpoints)
    azure_speech_endpoint_tts: str = ""

    azure_translator_key: str = ""
    azure_translator_region: str = ""     # e.g. centralindia ; leave empty for a *global* resource
    azure_translator_endpoint: str = "https://api.cognitive.microsofttranslator.com"

    mymemory_email: str = ""              # optional, raises MyMemory free quota to 50k chars/day
    google_free_endpoint: str = "https://translate.googleapis.com/translate_a/single"
    mymemory_endpoint: str = "https://api.mymemory.translated.net/get"

    elevenlabs_api_key: str = ""
    elevenlabs_voice: str = ""            # one premade voice id used for every language (eleven_v3 is multilingual)
    elevenlabs_voice_en: str = ""         # optional per-language overrides
    elevenlabs_model: str = "eleven_v3"   # v3 is the ElevenLabs model that supports Telugu

    google_tts_endpoint: str = "https://translate.google.com/translate_tts"

    voice_en: str = LANGUAGES["en"]["azure_voice"]
    voice_te: str = LANGUAGES["te"]["azure_voice"]
    voice_ta: str = LANGUAGES["ta"]["azure_voice"]
    voice_hi: str = LANGUAGES["hi"]["azure_voice"]

    http_port: int = 8000
    https_port: int = 8443
    provider_timeout_s: float = 10.0
    log_level: str = "info"

    extra: dict = field(default_factory=dict)

    # ---------- derived helpers ----------
    @property
    def azure_speech_configured(self) -> bool:
        return bool(self.azure_speech_key and (self.azure_speech_region or
                                               (self.azure_speech_endpoint_stt and self.azure_speech_endpoint_tts)))

    @property
    def azure_translator_configured(self) -> bool:
        return bool(self.azure_translator_key)

    def voice_for(self, lang: str) -> str:
        return getattr(self, f"voice_{lang}", "") or LANGUAGES[lang]["azure_voice"]

    def public_view(self) -> dict:
        """Safe-to-share summary (no secrets)."""
        return {
            "stt_provider": self.stt_provider,
            "translate_provider": self.translate_provider,
            "tts_provider": self.tts_provider,
            "azure_speech_configured": self.azure_speech_configured,
            "azure_speech_region": self.azure_speech_region or None,
            "azure_translator_configured": self.azure_translator_configured,
            "azure_translator_region": self.azure_translator_region or None,
            "elevenlabs_configured": bool(self.elevenlabs_api_key),
            "voices": {code: self.voice_for(code) for code in LANGUAGES},
        }


def _bool_env(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env_file: Path | None = None, environ: dict | None = None) -> Settings:
    file_values = parse_env_file(env_file if env_file is not None else ROOT_DIR / ".env")
    env = dict(file_values)
    env.update(environ if environ is not None else os.environ)

    def g(name: str, default: str = "") -> str:
        return (env.get(name) or default).strip()

    s = Settings(
        stt_provider=g("STT_PROVIDER", "auto").lower(),
        translate_provider=g("TRANSLATE_PROVIDER", "auto").lower(),
        tts_provider=g("TTS_PROVIDER", "auto").lower(),
        azure_speech_key=g("AZURE_SPEECH_KEY"),
        azure_speech_region=g("AZURE_SPEECH_REGION").lower().replace(" ", ""),
        azure_speech_endpoint_stt=g("AZURE_SPEECH_ENDPOINT_STT"),
        azure_speech_endpoint_tts=g("AZURE_SPEECH_ENDPOINT_TTS"),
        azure_translator_key=g("AZURE_TRANSLATOR_KEY"),
        azure_translator_region=g("AZURE_TRANSLATOR_REGION").lower().replace(" ", ""),
        azure_translator_endpoint=g("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com").rstrip("/"),
        mymemory_email=g("MYMEMORY_EMAIL"),
        google_free_endpoint=g("GOOGLE_FREE_ENDPOINT", "https://translate.googleapis.com/translate_a/single"),
        mymemory_endpoint=g("MYMEMORY_ENDPOINT", "https://api.mymemory.translated.net/get"),
        elevenlabs_api_key=g("ELEVENLABS_API_KEY"),
        elevenlabs_voice=g("ELEVENLABS_VOICE"),
        elevenlabs_voice_en=g("ELEVENLABS_VOICE_EN"),
        elevenlabs_model=g("ELEVENLABS_MODEL", "eleven_v3"),
        google_tts_endpoint=g("GOOGLE_TTS_ENDPOINT", "https://translate.google.com/translate_tts"),
        voice_en=g("AZURE_VOICE_EN", LANGUAGES["en"]["azure_voice"]),
        voice_te=g("AZURE_VOICE_TE", LANGUAGES["te"]["azure_voice"]),
        voice_ta=g("AZURE_VOICE_TA", LANGUAGES["ta"]["azure_voice"]),
        voice_hi=g("AZURE_VOICE_HI", LANGUAGES["hi"]["azure_voice"]),
        http_port=int(g("HTTP_PORT", "8000") or 8000),
        https_port=int(g("HTTPS_PORT", "8443") or 8443),
        provider_timeout_s=float(g("PROVIDER_TIMEOUT_S", "10") or 10),
        log_level=g("LOG_LEVEL", "info").lower(),
    )
    # "global" is not a real region for the Translator region header when the
    # resource is global; treat it as "don't send the header".
    if s.azure_translator_region == "global":
        s.azure_translator_region = ""
    return s
