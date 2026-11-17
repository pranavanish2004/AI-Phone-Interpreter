"""VAD, loop guard, sentence splitting, latency and config."""
import math
import struct

from server.config import Settings, load_settings, parse_env_file
from server.latency import LatencyStats, UtteranceTiming
from server.loopguard import LoopGuard, similarity
from server.sentences import split_sentences
from server.vad import FRAME_BYTES, VADConfig, VADSegmenter


def tone(ms, amp=6000, freq=220, rate=16000):
    n = rate * ms // 1000
    return b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))


def silence(ms, amp=40, rate=16000):
    n = rate * ms // 1000
    return b"".join(struct.pack("<h", amp if i % 2 else -amp) for i in range(n))


# ---------------------------------------------------------------- VAD
def test_vad_detects_one_utterance():
    v = VADSegmenter()
    events = v.feed(silence(500)) + v.feed(tone(800)) + v.feed(silence(900))
    kinds = [e[0] for e in events]
    assert kinds == ["start", "end"]
    pcm = events[1][1]
    assert 0.8 <= len(pcm) / 32000 <= 1.5  # ~0.8 s speech + preroll + a little tail


def test_vad_discards_click():
    v = VADSegmenter()
    events = v.feed(silence(300)) + v.feed(tone(80)) + v.feed(silence(900))
    assert [e[0] for e in events] in (["start", "discard"], [])


def test_vad_two_utterances_and_odd_chunks():
    v = VADSegmenter()
    audio = silence(400) + tone(600) + silence(900) + tone(700) + silence(900)
    events = []
    for i in range(0, len(audio), 777):  # deliberately not frame aligned (odd byte count)
        events += v.feed(audio[i:i + 777])
    assert [e[0] for e in events] == ["start", "end", "start", "end"]


def test_vad_max_length_cut_and_flush():
    v = VADSegmenter(VADConfig(max_utterance_ms=1000))
    events = v.feed(silence(200) + tone(2500))
    assert ("end" in [e[0] for e in events])
    assert v.flush()[0][0] in ("end", "discard")
    assert not v.in_speech


def test_vad_adapts_to_loud_background():
    v = VADSegmenter()
    v.feed(silence(2000, amp=300))   # steady fan noise
    assert v.noise_floor > 200
    assert v.feed(silence(500, amp=300)) == []


def test_frame_size():
    assert FRAME_BYTES == 640


# ---------------------------------------------------------------- loop guard
class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_loopguard_session_scope_gates_both_devices():
    c = Clock()
    g = LoopGuard(scope="session", tail_s=0.5, clock=c)
    assert not g.is_gated("laptop")
    g.playback_started("phone")
    assert g.is_gated("phone") and g.is_gated("laptop")
    g.playback_ended("phone")
    assert g.is_gated("laptop")          # tail
    c.t += 0.6
    assert not g.is_gated("laptop") and not g.is_gated("phone")


def test_loopguard_device_scope():
    c = Clock()
    g = LoopGuard(scope="device", clock=c)
    g.playback_started("phone")
    assert g.is_gated("phone") and not g.is_gated("laptop")


def test_loopguard_stuck_playback_expires():
    c = Clock()
    g = LoopGuard(max_play_s=10, clock=c)
    g.playback_started("phone")
    c.t += 11
    assert not g.is_gated("phone")


def test_loopguard_interrupt_opens_gate():
    c = Clock()
    g = LoopGuard(clock=c)
    g.playback_started("laptop")
    g.interrupt()
    assert not g.is_gated("phone")


def test_echo_only_right_after_playback():
    c = Clock()
    g = LoopGuard(tail_s=0.5, echo_after_s=1.0, clock=c)
    g.remember_played("మీరు ఎలా ఉన్నారు?")
    g.playback_started("phone")
    c.t += 2
    g.playback_ended("phone")
    c.t += 1
    assert g.echo_reason("మీరు ఎలా ఉన్నారు") is not None      # leaked echo
    assert g.echo_reason("I am going to the market") is None
    c.t += 10
    assert g.echo_reason("మీరు ఎలా ఉన్నారు") is None          # a deliberate reply later is fine


def test_short_replies_never_echo():
    c = Clock()
    g = LoopGuard(clock=c)
    g.remember_played("Hello")
    g.playback_started("laptop")
    g.playback_ended("laptop")
    assert g.echo_reason("hello") is None


def test_similarity():
    assert similarity("Hello, how are you?", "hello how are you") > 0.95
    assert similarity("hello", "goodbye my friend") < 0.5
    assert similarity("", "x") == 0.0


# ---------------------------------------------------------------- sentences
def test_split_sentences_english_and_telugu():
    assert split_sentences("Hello there. How are you today? I am fine, thanks!") == \
        ["Hello there.", "How are you today?", "I am fine, thanks!"]
    # a tiny trailing fragment is merged into its neighbour
    assert split_sentences("Hello there. How are you? Fine!") == ["Hello there.", "How are you? Fine!"]
    te = "నమస్కారం. మీరు ఎలా ఉన్నారు? నేను బాగున్నాను।"
    out = split_sentences(te)
    assert len(out) >= 2 and "".join(out).replace(" ", "") == te.replace(" ", "")


def test_split_merges_tiny_and_breaks_long():
    assert split_sentences("Hi. Ok. This is a longer sentence here.") == ["Hi. Ok. This is a longer sentence here."]
    long = ", ".join(["this is a clause"] * 30) + "."
    parts = split_sentences(long, max_chars=100)
    assert all(len(p) <= 100 for p in parts) and len(parts) > 3
    assert split_sentences("") == []
    assert split_sentences("Price is 3.5 rupees.") == ["Price is 3.5 rupees."]


# ---------------------------------------------------------------- latency
def test_latency_stats():
    st = LatencyStats()
    assert st.snapshot()["median_ms"] is None
    for v in (100, 200, 300, 400, 1000):
        st.add(v)
    snap = st.snapshot()
    assert snap["median_ms"] == 300 and snap["p90_ms"] == 1000 and snap["count"] == 5


def test_timing_summary():
    t = UtteranceTiming()
    for m in ("translate_start", "translate_done", "first_audio", "done"):
        t.mark(m)
    s = t.summary()
    assert s["stt_ms"] == 0.0 and s["first_audio_ms"] >= s["translate_ms"] >= 0


# ---------------------------------------------------------------- config
def test_env_parsing(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# c\nAZURE_SPEECH_KEY="abc"\nAZURE_SPEECH_REGION=Central India  # note\n'
                 "export TTS_PROVIDER=browser\nBROKEN\nAZURE_TRANSLATOR_REGION=global\n", encoding="utf-8")
    vals = parse_env_file(p)
    assert vals["AZURE_SPEECH_KEY"] == "abc" and vals["TTS_PROVIDER"] == "browser"
    s = load_settings(p, environ={})
    assert s.azure_speech_region == "centralindia"
    assert s.azure_translator_region == ""       # 'global' -> no region header
    assert s.azure_speech_configured and s.tts_provider == "browser"


def test_env_example_parses_to_defaults():
    from server.config import ROOT_DIR
    s = load_settings(ROOT_DIR / ".env.example", environ={})
    assert s.azure_speech_region == "" and s.azure_translator_region == ""
    assert not s.azure_speech_configured and not s.azure_translator_configured
    assert (s.stt_provider, s.translate_provider, s.tts_provider) == ("auto", "auto", "auto")
    assert s.http_port == 8000 and s.https_port == 8443


def test_public_view_has_no_secrets():
    s = Settings(azure_speech_key="SECRET1", azure_translator_key="SECRET2", elevenlabs_api_key="SECRET3",
                 azure_speech_region="centralindia")
    assert "SECRET" not in str(s.public_view())


def test_defaults_are_auto(tmp_path):
    s = load_settings(tmp_path / "missing.env", environ={})
    assert (s.stt_provider, s.translate_provider, s.tts_provider) == ("auto", "auto", "auto")
