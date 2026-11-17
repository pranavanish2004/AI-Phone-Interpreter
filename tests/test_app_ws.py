"""FastAPI app + WebSocket protocol, two devices in one session (mock providers)."""
import base64
import math
import struct
import time

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings
from server.loopguard import LoopGuard
from server.stt import MockSTT
from server.translate import ChainTranslator, MockTranslator
from server.tts import BrowserTTS, ChainTTS, MockTTS


def make_app(tts="mock", stt=True, **settings):
    s = Settings(**settings)
    tts_chain = ChainTTS([MockTTS(), BrowserTTS()]) if tts == "mock" else ChainTTS([BrowserTTS()])
    return create_app(s, translator=ChainTranslator([MockTranslator()]), tts=tts_chain,
                      server_stt=MockSTT() if stt else None,
                      loopguard_factory=lambda: LoopGuard(tail_s=0.05))


@pytest.fixture
def client():
    with TestClient(make_app()) as c:
        yield c


def recv_until(ws, mtype, limit=40, pred=None):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if m["type"] == mtype and (pred is None or pred(m)):
            return m, seen
    raise AssertionError(f"no {mtype} in {[x['type'] for x in seen]}")


def join(client, role, session="t1", **q):
    qs = "&".join(f"{k}={v}" for k, v in {"session": session, "role": role, **q}.items())
    ws = client.websocket_connect(f"/ws?{qs}")
    ws.__enter__()
    hello, _ = recv_until(ws, "hello")
    return ws, hello


def test_http_endpoints(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
    cfg = client.get("/api/config").json()
    assert cfg["roles"] == {"laptop": "en", "phone": "te"}
    assert "key" not in str(cfg).lower().replace("configured", "")
    code = client.get("/api/new-session").json()["session"]
    assert len(code) == 4 and code.isdigit()
    assert client.get("/static/index.html").status_code == 200


def test_hello_and_state(client):
    lap, hello = join(client, "laptop")
    assert hello["lang"] == "en" and hello["peer_lang"] == "te" and hello["stt_mode"] == "browser"
    ph, hello2 = join(client, "phone")
    assert hello2["lang"] == "te"
    st, _ = recv_until(lap, "state", pred=lambda m: m["devices"]["phone"] is not None)
    assert st["devices"]["laptop"]["lang"] == "en"
    lap.__exit__(None, None, None)
    st, _ = recv_until(ph, "state", pred=lambda m: m["devices"]["laptop"] is None)
    ph.__exit__(None, None, None)


def test_telugu_to_english_browser_text(client):
    lap, _ = join(client, "laptop")
    ph, _ = join(client, "phone")
    ph.send_json({"type": "partial", "text": "నమస"})
    m, _ = recv_until(lap, "transcript", pred=lambda m: not m["final"])
    assert m["role"] == "phone" and m["text"] == "నమస"
    ph.send_json({"type": "final", "text": "నమస్కారం"})
    tr, _ = recv_until(lap, "translation")
    assert tr["text"] == "Hello" and tr["lang"] == "en" and tr["role"] == "phone"
    audio, _ = recv_until(lap, "audio")
    assert audio["lang"] == "en" and audio["mime"] == "audio/wav"
    assert base64.b64decode(audio["data"])[:4] == b"RIFF" and audio["last"] is True
    lat, _ = recv_until(lap, "latency")
    assert lat["direction"] == "phone->laptop" and lat["src_lang"] == "te" and lat["dst_lang"] == "en"
    assert lat["first_audio_ms"] >= 0 and lat["stats"]["count"] == 1
    # the speaker sees its own transcript + translation too, but receives no audio
    _, seen = recv_until(ph, "latency")
    types = [x["type"] for x in seen]
    assert "translation" in types and "audio" not in types
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def test_english_to_telugu_with_browser_voice_fallback():
    with TestClient(make_app(tts="browser")) as client:
        lap, _ = join(client, "laptop", session="t2")
        ph, _ = join(client, "phone", session="t2")
        lap.send_json({"type": "final", "text": "How are you?"})
        sp, _ = recv_until(ph, "speak")
        assert sp["text"] == "మీరు ఎలా ఉన్నారు?" and sp["bcp47"] == "te-IN"
        lap.__exit__(None, None, None)
        ph.__exit__(None, None, None)


def test_multi_sentence_in_order(client):
    lap, _ = join(client, "laptop", session="t3")
    ph, _ = join(client, "phone", session="t3")
    lap.send_json({"type": "final", "text": "First sentence here. Second sentence here. Third one is here."})
    seqs = []
    for _ in range(3):
        a, _ = recv_until(ph, "audio")
        seqs.append((a["seq"], a["last"]))
    assert seqs == [(0, False), (1, False), (2, True)]
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def test_loop_guard_drops_speech_during_playback(client):
    lap, _ = join(client, "laptop", session="t4")
    ph, _ = join(client, "phone", session="t4")
    lap.send_json({"type": "playback", "state": "start"})
    g, _ = recv_until(ph, "gate")
    assert g["closed"] is True
    ph.send_json({"type": "final", "text": "Hello"})
    d, _ = recv_until(ph, "dropped")
    assert "playing" in d["reason"]
    lap.send_json({"type": "playback", "state": "end"})
    g, _ = recv_until(ph, "gate", pred=lambda m: m["closed"] is False)
    time.sleep(0.1)
    ph.send_json({"type": "final", "text": "నమస్కారం"})
    tr, _ = recv_until(lap, "translation")
    assert tr["text"] == "Hello"
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def test_interrupt_flushes_everyone(client):
    lap, _ = join(client, "laptop", session="t5")
    ph, _ = join(client, "phone", session="t5")
    ph.send_json({"type": "playback", "state": "start"})
    lap.send_json({"type": "interrupt"})
    f, _ = recv_until(ph, "flush")
    assert f["by"] == "laptop"
    g, _ = recv_until(ph, "gate", pred=lambda m: m["closed"] is False)
    lap.send_json({"type": "final", "text": "hello"})
    tr, _ = recv_until(ph, "translation")
    assert tr["text"] == "నమస్కారం"
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def pcm_tone(ms, amp=6000, rate=16000):
    return b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * 220 * i / rate))) for i in range(rate * ms // 1000))


def test_server_stt_mode_streams_pcm(client):
    lap, hello = join(client, "laptop", session="t6", stt_mode="server")
    assert hello["stt_mode"] == "server" and hello["server_stt_available"] is True
    ph, _ = join(client, "phone", session="t6")
    lap.send_json({"type": "mic", "on": True})
    audio = b"\x00\x00" * 8000 + pcm_tone(700) + b"\x00\x00" * 16000
    for i in range(0, len(audio), 640):
        lap.send_bytes(audio[i:i + 640])
    st, _ = recv_until(ph, "status", pred=lambda m: m["state"] == "speaking")
    tr, _ = recv_until(ph, "transcript", pred=lambda m: m["final"])
    assert tr["text"] == "hello" and tr["role"] == "laptop"
    a, _ = recv_until(ph, "audio")
    assert a["lang"] == "te"
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def test_server_mode_without_stt_reports_error():
    with TestClient(make_app(stt=False)) as client:
        lap, hello = join(client, "laptop", session="t7", stt_mode="server")
        assert hello["server_stt_available"] is False
        lap.send_json({"type": "mic", "on": True})
        audio = pcm_tone(600) + b"\x00\x00" * 16000
        for i in range(0, len(audio), 640):
            lap.send_bytes(audio[i:i + 640])
        e, _ = recv_until(lap, "error")
        assert e["where"] == "stt" and "Browser" in e["message"]
        lap.__exit__(None, None, None)


def test_peer_missing_notice(client):
    lap, _ = join(client, "laptop", session="t8")
    lap.send_json({"type": "final", "text": "hello"})
    n, seen = recv_until(lap, "notice")
    assert "not connected" in n["message"]
    assert any(x["type"] == "translation" for x in seen)
    lap.__exit__(None, None, None)


def test_same_role_replaces_old_connection(client):
    a, _ = join(client, "phone", session="t9")
    b, _ = join(client, "phone", session="t9")
    k, _ = recv_until(a, "kicked")
    assert "Another phone" in k["message"]
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_bad_role_rejected(client):
    ws = client.websocket_connect("/ws?session=x&role=tablet")
    ws.__enter__()
    m = ws.receive_json()
    assert m["type"] == "error"


def test_ping_pong_and_rtt(client):
    lap, _ = join(client, "laptop", session="t10")
    lap.send_json({"type": "ping", "t": 123})
    p, _ = recv_until(lap, "pong")
    assert p["t"] == 123
    lap.send_json({"type": "rtt", "ms": 42.5})
    lap.send_json({"type": "mic", "on": True})
    st, _ = recv_until(lap, "state", pred=lambda m: m["devices"]["laptop"]["mic_on"])
    assert st["devices"]["laptop"]["rtt_ms"] == 42.5
    lap.__exit__(None, None, None)


def test_translation_failure_reported():
    from server.http_util import ProviderError

    class Down(MockTranslator):
        name = "down"

        async def translate(self, *a):
            raise ProviderError("down", "service unavailable", 503)
    app = create_app(Settings(), translator=ChainTranslator([Down()]), tts=ChainTTS([BrowserTTS()]), server_stt=None)
    with TestClient(app) as client:
        lap, _ = join(client, "laptop", session="t11")
        lap.send_json({"type": "final", "text": "hello"})
        e, _ = recv_until(lap, "error")
        assert e["where"] == "translate" and "all providers failed" in e["message"]
        lap.__exit__(None, None, None)


def test_tamil_to_hindi_any_language_pair(client):
    lap, hello = join(client, "laptop", session="L1", lang="ta")
    assert hello["lang"] == "ta"
    ph, hello2 = join(client, "phone", session="L1", lang="hi")
    assert hello2["lang"] == "hi" and hello2["peer_lang"] == "ta"
    st, _ = recv_until(lap, "state", pred=lambda m: m["devices"]["phone"] is not None)
    assert st["devices"]["phone"]["lang"] == "hi" and st["devices"]["phone"]["lang_native"] == "हिन्दी"
    lap.send_json({"type": "final", "text": "வணக்கம்"})
    tr, _ = recv_until(ph, "translation")
    assert tr["lang"] == "hi" and tr["text"] == "[hi] வணக்கம்"          # mock translator shows target code
    a, _ = recv_until(ph, "audio")
    assert a["lang"] == "hi"
    ph.send_json({"type": "final", "text": "नमस्ते"})
    tr, _ = recv_until(lap, "translation", pred=lambda m: m["role"] == "phone")
    assert tr["lang"] == "ta"
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def test_same_language_passes_through(client):
    lap, _ = join(client, "laptop", session="L2", lang="te")
    ph, _ = join(client, "phone", session="L2", lang="te")
    lap.send_json({"type": "final", "text": "నమస్కారం"})
    tr, _ = recv_until(ph, "translation")
    assert tr["text"] == "నమస్కారం" and tr["provider"] == "same language"
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)


def test_change_language_mid_session_and_bad_lang(client):
    lap, hello = join(client, "laptop", session="L3", lang="xx")
    assert hello["lang"] == "en"                       # unknown -> seat default
    ph, _ = join(client, "phone", session="L3")
    ph.send_json({"type": "lang", "lang": "ta"})
    st, _ = recv_until(lap, "state", pred=lambda m: m["devices"]["phone"] and m["devices"]["phone"]["lang"] == "ta")
    lap.send_json({"type": "final", "text": "hello"})
    tr, _ = recv_until(ph, "translation")
    assert tr["lang"] == "ta"
    ph.send_json({"type": "lang", "lang": "klingon"})  # ignored
    ph.send_json({"type": "ping", "t": 1})
    recv_until(ph, "pong")
    lap.__exit__(None, None, None)
    ph.__exit__(None, None, None)
