"""Real provider classes against the local fake cloud (exact REST contracts)."""
import asyncio

import pytest

from server.http_util import ProviderError
from server.stt import AzureSTT, build_server_stt, default_client_mode, pcm16_to_wav, wav_to_pcm16
from server.translate import (AzureTranslator, ChainTranslator, GoogleFreeTranslator, MockTranslator,
                              MyMemoryTranslator, build_translator)
from server.tts import AzureTTS, BrowserTTS, ChainTTS, MockTTS, build_tts

run = asyncio.run


# ---------------------------------------------------------------- translation
def test_azure_translator_both_directions(cloud_settings):
    tr = AzureTranslator(cloud_settings())
    assert run(tr.translate("Hello", "en", "te")) == "AZ[te]:Hello"
    assert run(tr.translate("నమస్కారం", "te", "en")) == "AZ[en]:నమస్కారం"


def test_azure_translator_sends_region_header(cloud_settings, fake_cloud):
    from tests.conftest import FakeCloud
    FakeCloud.calls.clear()
    run(AzureTranslator(cloud_settings()).translate("Hi", "en", "te"))
    _, path, headers, q, _ = FakeCloud.calls[-1]
    assert path == "/translate"
    assert headers["Ocp-Apim-Subscription-Region"] == "centralindia"
    assert q["from"] == ["en"] and q["to"] == ["te"]


def test_azure_translator_401001_is_explained(cloud_settings):
    tr = AzureTranslator(cloud_settings(azure_translator_region=""))
    with pytest.raises(ProviderError) as ei:
        run(tr.translate("Hello", "en", "te"))
    assert ei.value.status == 401 and ei.value.code == "401001"
    assert "AZURE_TRANSLATOR_REGION" in ei.value.message


def test_custom_domain_endpoint_path():
    from server.config import Settings
    tr = AzureTranslator(Settings(azure_translator_key="k",
                                  azure_translator_endpoint="https://myres.cognitiveservices.azure.com"))
    assert tr._url() == "https://myres.cognitiveservices.azure.com/translator/text/v3.0/translate"
    assert AzureTranslator(Settings(azure_translator_key="k"))._url() == \
        "https://api.cognitive.microsofttranslator.com/translate"
    for pasted in ("https://myres.cognitiveservices.azure.com/translator/text/v3.0/",
                   "https://myres.cognitiveservices.azure.com/translator/text/v3.0/translate"):
        assert AzureTranslator(Settings(azure_translator_key="k", azure_translator_endpoint=pasted))._url() == \
            "https://myres.cognitiveservices.azure.com/translator/text/v3.0/translate"
    assert AzureTranslator(Settings(azure_translator_key="k",
                                    azure_translator_endpoint="https://api.cognitive.microsofttranslator.com/"))._url() \
        == "https://api.cognitive.microsofttranslator.com/translate"


def test_google_free_and_mymemory(cloud_settings):
    s = cloud_settings()
    assert run(GoogleFreeTranslator(s).translate("Hello", "en", "te")) == "G[te]:Hello"
    assert run(MyMemoryTranslator(s).translate("Hello", "en", "te")) == "M[en|te]:Hello"


def test_chain_falls_back_when_azure_unauthorized(cloud_settings):
    s = cloud_settings(azure_translator_key="wrong")
    chain = build_translator(s)
    assert [p.name for p in chain.providers] == ["azure", "google_free", "mymemory"]
    assert run(chain.translate("Hello", "en", "te")) == "G[te]:Hello"
    assert chain.last_provider == "google_free"
    assert any("401" in e for e in chain.last_errors)
    # azure now cooling down -> skipped without another 401 round trip
    from tests.conftest import FakeCloud
    FakeCloud.calls.clear()
    run(chain.translate("Again", "en", "te"))
    assert not any(c[1] == "/translate" for c in FakeCloud.calls)


def test_chain_second_fallback(cloud_settings):
    chain = build_translator(cloud_settings(azure_translator_key=""))
    assert [p.name for p in chain.providers] == ["google_free", "mymemory"]
    assert run(chain.translate("FAIL", "en", "te")) == "M[en|te]:FAIL"


def test_chain_all_fail_raises():
    class Bad(MockTranslator):
        name = "bad"

        async def translate(self, *a):
            raise ProviderError("bad", "boom", 500)
    with pytest.raises(ProviderError):
        run(ChainTranslator([Bad()]).translate("x", "en", "te"))


def test_explicit_provider_list_and_unknown():
    from server.config import Settings
    assert [p.name for p in build_translator(Settings(translate_provider="mymemory,mock")).providers] == \
        ["mymemory", "mock"]
    with pytest.raises(ValueError):
        build_translator(Settings(translate_provider="deepl"))


# ---------------------------------------------------------------- STT
def test_azure_stt_success_and_nomatch(cloud_settings):
    stt = AzureSTT(cloud_settings())
    assert run(stt.transcribe(b"\x01\x00" * 16000, "te")) == "heard te-IN"
    assert run(stt.transcribe(b"\x01\x00" * 10, "en")) == ""


def test_azure_stt_bad_key(cloud_settings):
    with pytest.raises(ProviderError) as ei:
        run(AzureSTT(cloud_settings(azure_speech_key="nope")).transcribe(b"\x00\x00" * 8000, "en"))
    assert ei.value.status == 401


def test_wav_roundtrip():
    pcm = bytes(range(256)) * 10
    data, rate = wav_to_pcm16(pcm16_to_wav(pcm))
    assert data == pcm and rate == 16000


def test_stt_mode_selection(cloud_settings):
    from server.config import Settings
    assert build_server_stt(Settings()) is None
    assert isinstance(build_server_stt(cloud_settings()), AzureSTT)
    assert default_client_mode(Settings()) == "browser"
    assert default_client_mode(Settings(stt_provider="azure")) == "server"


# ---------------------------------------------------------------- TTS
def test_azure_tts_mp3_and_ssml_escaping(cloud_settings):
    from tests.conftest import FakeCloud
    tts = AzureTTS(cloud_settings())
    res = run(tts.synthesize("Tom & Jerry <3", "te"))
    assert res.audio.startswith(b"ID3") and res.mime == "audio/mpeg"
    ssml = FakeCloud.calls[-1][4].decode()
    assert "te-IN-ShrutiNeural" in ssml and "Tom &amp; Jerry &lt;3" in ssml


class FakeEdgeModule:
    """Stands in for the `edge_tts` package (same Communicate/stream API)."""

    calls = []

    class Communicate:
        def __init__(self, text, voice, **kw):
            self.text, self.voice = text, voice
            FakeEdgeModule.calls.append((text, voice))

        async def stream(self):
            if self.text == "FAIL":
                raise RuntimeError("NoAudioReceived")
            yield {"type": "WordBoundary", "offset": 0}
            yield {"type": "audio", "data": b"ID3edge-"}
            yield {"type": "audio", "data": self.voice.encode()}


def test_edge_tts_uses_neural_voice_per_language():
    from server.config import Settings
    from server.tts import EdgeTTS
    e = EdgeTTS(Settings(), module=FakeEdgeModule)
    for lang, voice in (("te", "te-IN-ShrutiNeural"), ("ta", "ta-IN-PallaviNeural"),
                        ("hi", "hi-IN-SwaraNeural"), ("en", "en-IN-NeerjaNeural")):
        res = run(e.synthesize("hello", lang))
        assert res.audio == b"ID3edge-" + voice.encode() and res.mime == "audio/mpeg" and res.provider == "edge"


def test_edge_tts_errors_become_provider_errors():
    from server.config import Settings
    from server.tts import EdgeTTS
    with pytest.raises(ProviderError) as ei:
        run(EdgeTTS(Settings(), module=FakeEdgeModule).synthesize("FAIL", "te"))
    assert "NoAudioReceived" in ei.value.message


def test_edge_missing_package_message(monkeypatch):
    import builtins
    from server.config import Settings
    from server.tts import EdgeTTS
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "edge_tts":
            raise ImportError("nope")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert EdgeTTS.available() is False
    with pytest.raises(ProviderError) as ei:
        run(EdgeTTS(Settings()).synthesize("hi", "en"))
    assert "pip install edge-tts" in ei.value.message


def test_google_free_tts_and_long_text_split(cloud_settings):
    from server.tts import GoogleFreeTTS
    g = GoogleFreeTTS(cloud_settings())
    res = run(g.synthesize("నమస్కారం", "te"))
    assert res.audio.startswith(b"ID3[te:0/1]") and res.mime == "audio/mpeg"
    long_text = " ".join(["వాక్యం"] * 80)              # ~560 chars -> several requests
    res = run(g.synthesize(long_text, "ta"))
    assert res.audio.count(b"ID3") >= 3 and b"[ta:0/" in res.audio


def test_google_free_tts_rejects_html(cloud_settings):
    from server.tts import GoogleFreeTTS
    with pytest.raises(ProviderError):
        run(GoogleFreeTTS(cloud_settings()).synthesize("FAIL", "en"))


def test_split_for_google_limits():
    from server.tts import _split_for_google
    parts = _split_for_google("word " * 100 + "x" * 450)
    assert all(len(p) <= 190 for p in parts) and "".join(parts).replace(" ", "") == ("word" * 100 + "x" * 450)


def test_tts_chain_falls_back_azure_to_google(cloud_settings):
    chain = build_tts(cloud_settings(azure_speech_key="bad", tts_provider="azure,google"))
    res = run(chain.synthesize("hello", "en"))
    assert res.provider == "google" and res.audio.startswith(b"ID3")
    assert chain.last_errors and "401" in chain.last_errors[0]
    # azure is now cooling down: next call goes straight to google with no error
    res = run(chain.synthesize("again", "hi"))
    assert res.provider == "google" and chain.last_errors == []


def test_tts_chain_last_resort_is_browser(cloud_settings):
    chain = build_tts(cloud_settings(azure_speech_key="bad", tts_provider="azure,google"))
    res = run(chain.synthesize("FAIL", "en"))
    assert res.audio is None and res.provider == "browser" and len(chain.last_errors) == 2


def test_auto_chain_order(monkeypatch, cloud_settings):
    from server.config import Settings
    from server.tts import EdgeTTS
    monkeypatch.setattr(EdgeTTS, "available", staticmethod(lambda: True))
    assert [p.name for p in build_tts(cloud_settings()).providers] == ["azure", "edge", "google", "browser"]
    assert [p.name for p in build_tts(Settings()).providers] == ["edge", "google", "browser"]
    monkeypatch.setattr(EdgeTTS, "available", staticmethod(lambda: False))
    assert [p.name for p in build_tts(Settings()).providers] == ["google", "browser"]
    assert [p.name for p in build_tts(Settings(tts_provider="browser")).providers] == ["browser"]
    with pytest.raises(ValueError):
        build_tts(Settings(tts_provider="polly"))


def test_mock_tts_wav():
    res = run(MockTTS().synthesize("hello", "en"))
    assert res.audio[:4] == b"RIFF"


def test_elevenlabs_language_support():
    from server.config import Settings
    from server.tts import ElevenLabsTTS
    e = ElevenLabsTTS(Settings(elevenlabs_api_key="k", elevenlabs_voice="v"))           # default model eleven_v3
    assert all(e.supports(l) for l in ("en", "te", "ta", "hi"))
    old = ElevenLabsTTS(Settings(elevenlabs_api_key="k", elevenlabs_voice="v", elevenlabs_model="eleven_multilingual_v2"))
    assert old.supports("hi") and not old.supports("te")                                 # v2 has no Telugu
    assert not ElevenLabsTTS(Settings(elevenlabs_api_key="k")).supports("en")            # no voice id
    chain = ChainTTS([e, BrowserTTS()])
    assert chain.providers[0].name == "elevenlabs"


def test_azure_tts_voices_for_new_languages(cloud_settings):
    from tests.conftest import FakeCloud
    tts = AzureTTS(cloud_settings())
    run(tts.synthesize("வணக்கம்", "ta"))
    assert "ta-IN-PallaviNeural" in FakeCloud.calls[-1][4].decode()
    run(tts.synthesize("नमस्ते", "hi"))
    assert "hi-IN-SwaraNeural" in FakeCloud.calls[-1][4].decode()
