"""Two-device WebSocket smoke test against a RUNNING server.

    python scripts/ws_smoke.py                          # ws://localhost:8000
    python scripts/ws_smoke.py --url wss://192.168.1.20:8443 --insecure

Connects a fake laptop and a fake phone to one session, sends one sentence in
each direction as browser-recognised text, and checks that each side gets the
translation plus audio (or a speak-text fallback). Uses whatever providers the
server is configured with - so with real keys this is a real end-to-end test
of translation + TTS (everything except the microphone).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import sys
import time


async def recv_until(ws, mtype, timeout=25.0, role=None):
    end = time.monotonic() + timeout
    while True:
        left = end - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"no '{mtype}' message within {timeout}s")
        m = json.loads(await asyncio.wait_for(ws.recv(), left))
        if m["type"] == "error":
            print(f"   ! server error: {m.get('where')}: {m.get('message')}")
        if m["type"] == mtype and (role is None or m.get("role") == role):
            return m


async def main(url: str, insecure: bool) -> int:
    import websockets
    ctx = None
    if url.startswith("wss"):
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
    session = f"smoke{int(time.time()) % 100000}"
    kw = {"ssl": ctx} if ctx else {}
    async with websockets.connect(f"{url}/ws?session={session}&role=laptop&stt_mode=browser", **kw) as lap, \
            websockets.connect(f"{url}/ws?session={session}&role=phone&stt_mode=browser", **kw) as ph:
        await recv_until(lap, "hello")
        await recv_until(ph, "hello")
        ok = True
        for speaker, listener, text, name, role in (
                (ph, lap, "నమస్కారం, మీరు ఎలా ఉన్నారు?", "TE->EN", "phone"),
                (lap, ph, "Hello, where is the railway station?", "EN->TE", "laptop")):
            t0 = time.perf_counter()
            await speaker.send(json.dumps({"type": "final", "text": text}))
            try:
                tr = await recv_until(listener, "translation", role=role)
                while True:
                    m = json.loads(await asyncio.wait_for(listener.recv(), 25))
                    if m["type"] in ("audio", "speak"):
                        break
                dt = (time.perf_counter() - t0) * 1000
                kind = f"audio {m.get('mime')} via {m.get('provider')}" if m["type"] == "audio" else "speak-text (device voice)"
                print(f"[OK]   {name}: '{text}' -> '{tr['text']}' [{tr.get('provider')}]  first output {dt:.0f} ms, {kind}")
                # report playback so the loop guard reopens
                await listener.send(json.dumps({"type": "playback", "state": "start"}))
                await listener.send(json.dumps({"type": "playback", "state": "end"}))
                await asyncio.sleep(0.8)
            except Exception as e:
                ok = False
                print(f"[FAIL] {name}: {e}")
        return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8000")
    ap.add_argument("--insecure", action="store_true", help="accept the self-signed certificate")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(asyncio.run(main(a.url.rstrip("/"), a.insecure)))
