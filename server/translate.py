"""Text translation providers.

* AzureTranslator   - Azure AI Translator v3 (free F0 tier: 2M chars/month).
* GoogleFreeTranslator - Google's public "gtx" web endpoint. Free, no key,
  unofficial (may rate-limit); used as a fallback.
* MyMemoryTranslator - api.mymemory.translated.net. Free, no key
  (5k chars/day anonymous, 50k with MYMEMORY_EMAIL).
* MockTranslator    - deterministic, for tests only.

`ChainTranslator` tries providers in order and remembers which one worked,
so a broken Azure key does not take the interpreter down.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from .config import LANGUAGES, Settings
from .http_util import ProviderError, request, short

log = logging.getLogger("interpreter.translate")

AZURE_AUTH_HINT = (
    "Azure Translator rejected the credentials (401). Usual causes: "
    "(1) AZURE_TRANSLATOR_REGION missing/wrong - it must equal the resource's "
    "'Location' in the Azure portal (e.g. centralindia) for a regional or "
    "multi-service resource, and must be EMPTY for a 'Global' resource; "
    "(2) a Speech key was pasted instead of the Translator key; "
    "(3) the key was regenerated. Run: python scripts/stage1_probe.py --translator-diagnose"
)


class Translator:
    name = "base"

    async def translate(self, text: str, src: str, dst: str) -> str:  # pragma: no cover
        raise NotImplementedError


class MockTranslator(Translator):
    name = "mock"
    PHRASES = {
        ("te", "en"): {"నమస్కారం": "Hello", "మీరు ఎలా ఉన్నారు?": "How are you?"},
        ("en", "te"): {"hello": "నమస్కారం", "how are you?": "మీరు ఎలా ఉన్నారు?"},
    }

    async def translate(self, text: str, src: str, dst: str) -> str:
        table = self.PHRASES.get((src, dst), {})
        hit = table.get(text.strip()) or table.get(text.strip().lower())
        return hit or f"[{dst}] {text}"


class AzureTranslator(Translator):
    name = "azure"

    def __init__(self, settings: Settings, region_override: str | None = None):
        self.key = settings.azure_translator_key
        self.region = settings.azure_translator_region if region_override is None else region_override
        self.endpoint = settings.azure_translator_endpoint.rstrip("/")
        self.timeout = settings.provider_timeout_s

    def _headers(self) -> dict:
        h = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/json; charset=UTF-8",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        if self.region:
            h["Ocp-Apim-Subscription-Region"] = self.region
        return h

    def _url(self) -> str:
        # Accept the endpoint with or without path pieces copied from the portal.
        base = self.endpoint.rstrip("/")
        for suffix in ("/translate", "/translator/text/v3.0", "/translator/text/v3.0/"):
            if base.endswith(suffix.rstrip("/")):
                base = base[: -len(suffix.rstrip("/"))].rstrip("/")
        # A custom-domain endpoint (https://<name>.cognitiveservices.azure.com)
        # needs the /translator/text/v3.0 path; the global endpoint does not.
        if "cognitiveservices.azure.com" in base:
            return f"{base}/translator/text/v3.0/translate"
        return f"{base}/translate"

    async def translate(self, text: str, src: str, dst: str) -> str:
        if not self.key:
            raise ProviderError(self.name, "AZURE_TRANSLATOR_KEY is not set")
        params = {"api-version": "3.0", "from": LANGUAGES[src]["translator"], "to": LANGUAGES[dst]["translator"]}
        body = json.dumps([{"Text": text}], ensure_ascii=False).encode("utf-8")
        resp = await request("POST", self._url(), provider=self.name, headers=self._headers(),
                             data=body, params=params, timeout=self.timeout)
        if resp.status != 200:
            code = None
            msg = short(resp.text())
            try:
                err = resp.json().get("error", {})
                code = str(err.get("code")) if err.get("code") is not None else None
                msg = err.get("message", msg)
            except Exception:
                pass
            if resp.status == 401:
                msg = f"{msg} | {AZURE_AUTH_HINT}"
            raise ProviderError(self.name, f"HTTP {resp.status} code={code}: {msg}", resp.status, code)
        data = resp.json()
        return data[0]["translations"][0]["text"]


class GoogleFreeTranslator(Translator):
    name = "google_free"

    def __init__(self, settings: Settings):
        self.endpoint = settings.google_free_endpoint
        self.timeout = settings.provider_timeout_s

    async def translate(self, text: str, src: str, dst: str) -> str:
        params = {"client": "gtx", "sl": LANGUAGES[src]["translator"], "tl": LANGUAGES[dst]["translator"],
                  "dt": "t", "q": text}
        resp = await request("GET", self.endpoint, provider=self.name, params=params, timeout=self.timeout,
                             headers={"User-Agent": "Mozilla/5.0"})
        if resp.status != 200:
            raise ProviderError(self.name, f"HTTP {resp.status}: {short(resp.text())}", resp.status)
        data = resp.json()
        out = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])
        if not out.strip():
            raise ProviderError(self.name, "empty translation")
        return out


class MyMemoryTranslator(Translator):
    name = "mymemory"

    def __init__(self, settings: Settings):
        self.endpoint = settings.mymemory_endpoint
        self.email = settings.mymemory_email
        self.timeout = settings.provider_timeout_s

    async def translate(self, text: str, src: str, dst: str) -> str:
        params = {"q": text, "langpair": f"{LANGUAGES[src]['translator']}|{LANGUAGES[dst]['translator']}"}
        if self.email:
            params["de"] = self.email
        resp = await request("GET", self.endpoint, provider=self.name, params=params, timeout=self.timeout)
        if resp.status != 200:
            raise ProviderError(self.name, f"HTTP {resp.status}: {short(resp.text())}", resp.status)
        data = resp.json()
        status = int(data.get("responseStatus", 200) or 200)
        out = (data.get("responseData") or {}).get("translatedText") or ""
        if status != 200 or not out.strip():
            raise ProviderError(self.name, f"status {status}: {short(str(data.get('responseDetails', '')))}", status)
        if "MYMEMORY WARNING" in out.upper():
            raise ProviderError(self.name, "daily free quota exhausted", 429)
        return out


class ChainTranslator(Translator):
    """Try each provider in order; skip ones that fail with auth/quota errors for a while."""

    name = "chain"
    COOLDOWN_S = 300.0  # after an auth/quota failure, don't retry that provider for 5 minutes

    def __init__(self, providers: list[Translator]):
        if not providers:
            raise ValueError("no translation providers")
        self.providers = providers
        self._disabled_until: dict[str, float] = {}
        self.last_provider: str | None = None
        self.last_errors: list[str] = []

    async def translate(self, text: str, src: str, dst: str) -> str:
        errors: list[str] = []
        now = time.monotonic()
        candidates = [p for p in self.providers if self._disabled_until.get(p.name, 0) <= now]
        if not candidates:  # everything cooling down - try them all anyway
            candidates = list(self.providers)
        for p in candidates:
            try:
                out = await p.translate(text, src, dst)
                self.last_provider = p.name
                self.last_errors = errors
                return out
            except ProviderError as e:
                errors.append(str(e))
                log.warning("translation provider failed: %s", e)
                if e.status in (401, 403, 429) or "not set" in e.message:
                    self._disabled_until[p.name] = time.monotonic() + self.COOLDOWN_S
            except Exception as e:  # malformed response etc.
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                log.warning("translation provider crashed: %s", e)
        self.last_errors = errors
        raise ProviderError("translate", "all providers failed: " + " || ".join(errors))


def build_translator(settings: Settings) -> ChainTranslator:
    choice = settings.translate_provider
    makers = {
        "azure": lambda: AzureTranslator(settings),
        "google_free": lambda: GoogleFreeTranslator(settings),
        "mymemory": lambda: MyMemoryTranslator(settings),
        "mock": lambda: MockTranslator(),
    }
    if choice == "auto":
        names = (["azure"] if settings.azure_translator_configured else []) + ["google_free", "mymemory"]
    else:
        names = [n.strip() for n in choice.split(",") if n.strip()]
    unknown = [n for n in names if n not in makers]
    if unknown:
        raise ValueError(f"unknown TRANSLATE_PROVIDER(s): {unknown}; choose from {sorted(makers)}")
    return ChainTranslator([makers[n]() for n in names])
