"""Browser end-to-end test: real Chromium "laptop" + "phone" against a running server.

    python scripts/e2e_browser.py [--base-http http://localhost:8000] [--base-https https://localhost:8443]

Needs: pip install playwright && playwright install chromium   (developer tool, not needed to run the app)
Start the server first with mock providers for a deterministic run:
    set STT_PROVIDER=mock & set TRANSLATE_PROVIDER=mock & set TTS_PROVIDER=mock & python run.py

What it checks
  1. both devices join one session and see each other online
  2. browser-recognition mode: phone speaks (fake SpeechRecognition) -> laptop shows live
     partial + final transcript + translation and PLAYS audio through Web Audio
  3. feedback-loop guard: while the laptop plays, the phone's recognition is paused
  4. reverse direction laptop -> phone
  5. interrupt button flushes playback
  6. server-recognition mode: Chromium fake microphone -> AudioWorklet -> 16 kHz PCM over
     the WebSocket -> server VAD -> STT -> translation -> phone
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

FAKE_SR = r"""
(() => {
  class FakeRec {
    constructor() { this.lang = ''; this.continuous = false; this.interimResults = false; window.__fakeRecs = (window.__fakeRecs||[]); }
    start() { this.active = true; window.__fakeRec = this; window.__recStarts = (window.__recStarts||0) + 1; setTimeout(() => this.onstart && this.onstart(), 10); }
    abort() { if (!this.active) return; this.active = false; window.__recAborts = (window.__recAborts||0) + 1; setTimeout(() => this.onend && this.onend(), 10); }
    stop() { this.abort(); }
    emit(text, final) {
      if (!this.active) return false;
      const alt = { transcript: text, confidence: 0.9 };
      const res = [alt]; res.isFinal = !!final;
      const results = [res];
      this.onresult && this.onresult({ resultIndex: 0, results });
      return true;
    }
  }
  window.SpeechRecognition = FakeRec; window.webkitSpeechRecognition = FakeRec;
})();
"""


def speechy_wav(path: Path) -> None:
    rate = 48000
    frames = bytearray()

    def add(ms, amp):
        n = rate * ms // 1000
        for i in range(n):
            v = int(amp * math.sin(2 * math.pi * 210 * i / rate) * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / rate)))
            frames.extend(struct.pack("<h", v))
    for _ in range(3):
        add(1200, 30)      # silence
        add(900, 12000)    # "speech"
        add(1500, 30)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def wait_for(fn, timeout=10.0, what="condition"):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.1)
    raise AssertionError(f"timeout waiting for {what}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-http", default="http://localhost:8000")
    ap.add_argument("--base-https", default="https://localhost:8443")
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp())
    wav = tmp / "speech.wav"
    speechy_wav(wav)
    shots = Path(a.shots) if a.shots else None
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
            print(f"[PASS] {name}")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"[FAIL] {name}: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={wav}",
        ])
        lap_ctx = browser.new_context(viewport={"width": 1100, "height": 800})
        ph_ctx = browser.new_context(viewport={"width": 390, "height": 800}, ignore_https_errors=True,
                                     user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
                                                "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
                                     is_mobile=True, has_touch=True)
        for c in (lap_ctx, ph_ctx):
            c.add_init_script(FAKE_SR)
        lap, ph = lap_ctx.new_page(), ph_ctx.new_page()
        logs = []
        for name, pg in (("laptop", lap), ("phone", ph)):
            pg.on("console", lambda m, n=name: logs.append(f"{n}: {m.text}"))
            pg.on("pageerror", lambda e, n=name: logs.append(f"{n} PAGEERROR: {e}"))

        session = f"e2e{int(time.time()) % 10000}"
        lap.goto(f"{a.base_http}/?session={session}&role=laptop&stt=browser")
        ph.goto(f"{a.base_https}/?session={session}&role=phone&stt=browser")

        def join():
            assert "suggested" in ph.get_attribute('.role-btn[data-role="phone"]', "class")
            lap.click('.role-btn[data-role="laptop"]')
            ph.click('.role-btn[data-role="phone"]')
            wait_for(lambda: "online" in lap.get_attribute("#dev-phone", "class"), what="phone online on laptop")
            wait_for(lambda: "online" in ph.get_attribute("#dev-laptop", "class"), what="laptop online on phone")
            assert lap.text_content("#sessionLabel") == session
            assert ph.evaluate("window.isSecureContext") is True
        check("1. both devices join and see each other", join)
        if shots:
            lap.screenshot(path=str(shots / "laptop_joined.png"))
            ph.screenshot(path=str(shots / "phone_joined.png"))

        def te_to_en():
            ph.click("#micBtn")
            wait_for(lambda: ph.evaluate("!!(window.__fakeRec && window.__fakeRec.active)"), what="phone recognizer start")
            ph.evaluate("window.__fakeRec.emit('నమస', false)")
            wait_for(lambda: "నమస" in (lap.text_content(".bubble.partial") or ""), what="partial on laptop")
            ph.evaluate("window.__fakeRec.emit('నమస్కారం', true)")
            wait_for(lambda: "Hello" in (lap.text_content(".bubble.from-phone .trans") or ""), what="translation on laptop")
            assert "నమస్కారం" in lap.text_content(".bubble.from-phone .orig")
            assert "Hello" in ph.text_content(".bubble.from-phone .trans")  # speaker sees it too
            # laptop must actually start playing
            wait_for(lambda: lap.evaluate("window.__interp.localPlaying") or
                     "Playing" in lap.text_content("#playText"), timeout=5, what="laptop playback")
        check("2. phone Telugu -> laptop English transcript, translation, audio playback", te_to_en)

        def loop_guard():
            # while the laptop plays, the phone must be paused (gate) - check either now or that it happened
            paused_seen = wait_for(lambda: ph.evaluate("window.__interp.gateClosed") or
                                   ph.evaluate("(window.__recAborts||0) > 0"), timeout=5, what="phone paused")
            assert paused_seen
            # after playback the phone resumes listening
            wait_for(lambda: not lap.evaluate("window.__interp.localPlaying"), timeout=10, what="laptop playback end")
            wait_for(lambda: not ph.evaluate("window.__interp.gateClosed"), timeout=5, what="gate reopened")
            wait_for(lambda: ph.evaluate("!!(window.__fakeRec && window.__fakeRec.active)"), timeout=5,
                     what="phone recognizer restarted")
            assert "Listening" in ph.text_content("#micLabel")
        check("3. loop guard pauses the phone mic while the laptop plays, then resumes", loop_guard)

        def en_to_te():
            lap.click("#micBtn")
            wait_for(lambda: lap.evaluate("!!(window.__fakeRec && window.__fakeRec.active)"), what="laptop recognizer")
            lap.evaluate("window.__fakeRec.emit('hello', true)")
            wait_for(lambda: "నమస్కారం" in (ph.text_content(".bubble.from-laptop .trans") or ""), what="te translation on phone")
            wait_for(lambda: ph.evaluate("window.__interp.localPlaying"), timeout=5, what="phone playback")
            wait_for(lambda: lap.text_content("#latFirst") not in ("–", ""), what="latency shown")
        check("4. laptop English -> phone Telugu with playback + latency display", en_to_te)
        if shots:
            lap.screenshot(path=str(shots / "laptop_conversation.png"))
            ph.screenshot(path=str(shots / "phone_conversation.png"))

        def interrupt():
            wait_for(lambda: not ph.evaluate("window.__interp.localPlaying"), timeout=10, what="phone idle")
            time.sleep(0.8)
            lap.evaluate("window.__fakeRec.emit('This is a much longer sentence for testing. It has two parts here.', true)")
            wait_for(lambda: ph.evaluate("window.__interp.localPlaying"), timeout=5, what="phone playing long")
            ph.click("#interruptBtn")
            wait_for(lambda: not ph.evaluate("window.__interp.localPlaying"), timeout=3, what="phone stopped")
            wait_for(lambda: not lap.evaluate("window.__interp.gateClosed"), timeout=3, what="laptop gate open")
        check("5. interrupt stops playback on the phone and reopens both mics", interrupt)

        def server_mode():
            # turn laptop mic off, switch to server (Azure/mock) recognition, fake mic streams PCM
            lap.click("#micBtn")
            lap.click("#settingsBtn")
            lap.click('#modeSeg button[data-mode="server"]')
            lap.click("#closeDrawer")
            before = ph.locator(".bubble.from-laptop").count()
            lap.click("#micBtn")
            wait_for(lambda: lap.evaluate("!!(window.__interp.streamer && window.__interp.streamer.active)"),
                     what="audio worklet streaming")
            wait_for(lambda: ph.locator(".bubble.from-laptop").count() > before, timeout=15,
                     what="server-recognised utterance arriving on phone")
            txt = ph.locator(".bubble.from-laptop .orig").last.text_content()
            assert "hello" in txt, txt
            lap.click("#micBtn")
        check("6. server mode: fake mic -> AudioWorklet -> PCM WS -> VAD -> STT -> phone", server_mode)

        def tamil_and_hindi():
            # language chips show the chosen languages
            assert "తెలుగు" in lap.text_content("#dev-phone .card-lang")
            assert "English" in ph.text_content("#dev-laptop .card-lang")
            # phone switches to Tamil from Settings, laptop switches to Hindi
            ph.click("#settingsBtn")
            ph.select_option("#langSelectCall", "ta")
            ph.click("#closeDrawer")
            lap.click("#settingsBtn")
            lap.select_option("#langSelectCall", "hi")
            lap.click("#closeDrawer")
            wait_for(lambda: "தமிழ்" in lap.text_content("#dev-phone .card-lang"), what="Tamil chip on laptop")
            wait_for(lambda: "हिन्दी" in ph.text_content("#dev-laptop .card-lang"), what="Hindi chip on phone")
            ph.click("#micBtn") if not ph.evaluate("window.__interp.micOn") else None
            wait_for(lambda: ph.evaluate("!!(window.__fakeRec && window.__fakeRec.active && window.__fakeRec.lang === 'ta-IN')"),
                     what="phone recognizer restarted in ta-IN")
            ph.evaluate("window.__fakeRec.emit('வணக்கம் நண்பா', true)")
            wait_for(lambda: "[hi]" in (lap.locator(".bubble.from-phone .trans").last.text_content() or ""),
                     what="Tamil->Hindi translation on laptop")
            assert lap.locator(".bubble.from-phone .orig .lbl").last.text_content() == "TA"
        check("7. Tamil (phone) -> Hindi (laptop) via in-call language switch", tamil_and_hindi)
        if shots:
            lap.screenshot(path=str(shots / "laptop_multilang.png"))
            ph.screenshot(path=str(shots / "phone_multilang.png"))

        errors = [l for l in logs if "PAGEERROR" in l]
        check("8. no JavaScript errors", lambda: (_ for _ in ()).throw(AssertionError("; ".join(errors))) if errors else None)
        browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} browser checks passed")
    if failed:
        print("console tail:\n  " + "\n  ".join(logs[-25:]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
