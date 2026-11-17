"""Real-provider self test (used by /api/selftest and scripts/stage1_probe.py).

Each check calls the real cloud service and reports ok / milliseconds /
output / error. Keys are never included in the report.
"""
from __future__ import annotations

import time
from dataclasses import replace

from .config import Settings
from .http_util import ProviderError
from .loopguard import similarity
from .stt import AzureSTT, wav_to_pcm16
from .translate import AzureTranslator, GoogleFreeTranslator, MyMemoryTranslator
from .tts import AzureTTS, EdgeTTS, GoogleFreeTTS

SAMPLES = {
    ("en", "te"): "Hello, how are you? Where is the bus stand?",
    ("te", "en"): "నమస్కారం, మీరు ఎలా ఉన్నారు?",
}
EXTRA_SAMPLES = {   # checked with the free Google translator only (keeps the probe quick)
    ("en", "ta"): "Hello, how are you?",
    ("ta", "en"): "வணக்கம், எப்படி இருக்கிறீர்கள்?",
    ("en", "hi"): "Hello, how are you?",
    ("hi", "en"): "नमस्ते, आप कैसे हैं?",
}
VOICE_SAMPLES = {
    "en": "Hello, this is a voice test.",
    "te": "నమస్కారం, ఇది వాయిస్ పరీక్ష.",
    "ta": "வணக்கம், இது குரல் சோதனை.",
    "hi": "नमस्ते, यह आवाज़ परीक्षण है।",
}


async def _timed(coro):
    t = time.perf_counter()
    try:
        out = await coro
        return True, round((time.perf_counter() - t) * 1000), out, None
    except ProviderError as e:
        return False, round((time.perf_counter() - t) * 1000), None, e.message
    except Exception as e:
        return False, round((time.perf_counter() - t) * 1000), None, f"{type(e).__name__}: {e}"


async def check_translation(settings: Settings) -> list[dict]:
    providers = []
    if settings.azure_translator_configured:
        providers.append(AzureTranslator(settings))
    providers += [GoogleFreeTranslator(settings), MyMemoryTranslator(settings)]
    results = []
    for p in providers:
        for (src, dst), text in SAMPLES.items():
            ok, ms, out, err = await _timed(p.translate(text, src, dst))
            results.append({"check": f"translate {src}->{dst}", "provider": p.name, "ok": ok, "ms": ms,
                            "input": text, "output": out, "error": err})
    g = GoogleFreeTranslator(settings)
    for (src, dst), text in EXTRA_SAMPLES.items():
        ok, ms, out, err = await _timed(g.translate(text, src, dst))
        results.append({"check": f"translate {src}->{dst}", "provider": g.name, "ok": ok, "ms": ms,
                        "input": text, "output": out, "error": err})
    if not settings.azure_translator_configured:
        results.append({"check": "translate", "provider": "azure", "ok": False, "ms": 0,
                        "error": "skipped: AZURE_TRANSLATOR_KEY not set (free fallbacks are used instead)"})
    return results


async def diagnose_azure_translator(settings: Settings) -> list[dict]:
    """Try the region-header variants that cause most 401001 errors."""
    if not settings.azure_translator_configured:
        return [{"variant": "-", "ok": False, "error": "AZURE_TRANSLATOR_KEY not set"}]
    variants: list[tuple[str, str]] = []
    seen = set()
    for label, region in [("configured region", settings.azure_translator_region),
                          ("no region header (global resource)", ""),
                          ("speech region", settings.azure_speech_region),
                          ("centralindia", "centralindia"), ("southindia", "southindia"),
                          ("westindia", "westindia"), ("eastus", "eastus"), ("westeurope", "westeurope"),
                          ("'global' header", "global")]:
        if region in seen:
            continue
        seen.add(region)
        variants.append((label, region))
    out = []
    same_as_speech = bool(settings.azure_speech_key) and settings.azure_speech_key == settings.azure_translator_key
    for label, region in variants:
        tr = AzureTranslator(settings, region_override=region)
        ok, ms, text, err = await _timed(tr.translate("Hello", "en", "te"))
        out.append({"variant": label, "region_header": region or None, "ok": ok, "ms": ms,
                    "output": text, "error": (err or "")[:160] or None})
        if ok:
            break
    if same_as_speech:
        out.append({"variant": "note", "ok": None,
                    "error": "AZURE_TRANSLATOR_KEY is identical to AZURE_SPEECH_KEY. That only works for a "
                             "multi-service 'Azure AI services' resource; a Speech-only key is rejected (401001)."})
    return out


async def check_speech(settings: Settings) -> list[dict]:
    if not settings.azure_speech_configured:
        return [{"check": "azure speech", "provider": "azure", "ok": False, "ms": 0,
                 "error": "skipped: AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set "
                          "(browser speech recognition and browser voices will be used)"}]
    tts = AzureTTS(settings)
    stt = AzureSTT(settings)
    results = []
    for lang, text in (("te", SAMPLES[("te", "en")]), ("en", SAMPLES[("en", "te")])):
        ok, ms, res, err = await _timed(tts.synthesize(text, lang))
        results.append({"check": f"tts {lang} (mp3)", "provider": "azure", "ok": ok, "ms": ms,
                        "output": f"{len(res.audio)} bytes {res.mime}" if ok else None, "error": err})
        # round trip: synthesize 16 kHz WAV, then recognise it again
        ok, ms, res, err = await _timed(tts.synthesize(text, lang, output_format="riff-16khz-16bit-mono-pcm"))
        if not ok:
            results.append({"check": f"stt {lang}", "provider": "azure", "ok": False, "ms": 0,
                            "error": f"could not create test audio: {err}"})
            continue
        try:
            pcm, _rate = wav_to_pcm16(res.audio)
        except Exception as e:
            results.append({"check": f"stt {lang}", "provider": "azure", "ok": False, "ms": 0,
                            "error": f"bad test audio: {e}"})
            continue
        ok, ms, heard, err = await _timed(stt.transcribe(pcm, lang))
        score = round(similarity(text, heard or ""), 2) if ok else None
        results.append({"check": f"stt {lang} (round trip)", "provider": "azure", "ok": bool(ok and heard),
                        "ms": ms, "input": text, "output": heard, "similarity": score, "error": err})
    return results


async def check_free_voices(settings: Settings) -> list[dict]:
    """Edge TTS (if installed) and Google voice, every language."""
    providers = []
    if EdgeTTS.available():
        providers.append(EdgeTTS(settings))
    else:
        providers.append(None)
    providers.append(GoogleFreeTTS(settings))
    results = []
    for p in providers:
        if p is None:
            results.append({"check": "voice (all languages)", "provider": "edge", "ok": False, "ms": 0,
                            "error": "skipped: edge-tts not installed - run: python -m pip install edge-tts"})
            continue
        for lang, text in VOICE_SAMPLES.items():
            ok, ms, res, err = await _timed(p.synthesize(text, lang))
            results.append({"check": f"voice {lang}", "provider": p.name, "ok": ok, "ms": ms,
                            "output": f"{len(res.audio)} bytes {res.mime}" if ok else None, "error": err})
    return results


async def run_all(settings: Settings, diagnose: bool = False) -> dict:
    report = {
        "settings": settings.public_view(),
        "translation": await check_translation(settings),
        "voices": await check_free_voices(settings),
        "speech": await check_speech(settings),
    }
    azure_tr_failed = any(r["provider"] == "azure" and r["ok"] is False and "skipped" not in (r["error"] or "")
                          for r in report["translation"])
    if diagnose or azure_tr_failed:
        report["azure_translator_diagnosis"] = await diagnose_azure_translator(replace(settings))
    report["summary"] = summarize(report)
    return report


def summarize(report: dict) -> dict:
    tr_ok = {r["provider"] for r in report["translation"] if r["ok"]}
    tr_dirs = {r["check"] for r in report["translation"] if r["ok"]}
    sp = {r["check"]: r["ok"] for r in report["speech"]}
    voices: dict[str, list[str]] = {}
    for r in report.get("voices", []):
        if r["ok"]:
            voices.setdefault(r["check"].split()[-1], []).append(r["provider"])
    if sp.get("tts te (mp3)"):
        voices.setdefault("te", []).insert(0, "azure")
    if sp.get("tts en (mp3)"):
        voices.setdefault("en", []).insert(0, "azure")
    return {
        "server_voice_by_language": {lang: voices.get(lang, []) for lang in VOICE_SAMPLES},
        "translation_working": sorted(tr_ok),
        "both_directions_translate": {"translate en->te", "translate te->en"} <= tr_dirs,
        "azure_tts_te": bool(sp.get("tts te (mp3)")),
        "azure_tts_en": bool(sp.get("tts en (mp3)")),
        "azure_stt_te": bool(sp.get("stt te (round trip)")),
        "azure_stt_en": bool(sp.get("stt en (round trip)")),
    }
