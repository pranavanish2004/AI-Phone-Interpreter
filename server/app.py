"""FastAPI application: static UI, REST helpers and the device WebSocket.

WebSocket protocol (/ws?session=<code>&role=laptop|phone&lang=en|te|ta|hi)
---------------------------------------------------------
client -> server (JSON text frames)
    {"type":"mode", "stt_mode":"browser"|"server"}
    {"type":"lang", "lang":"en"|"te"|"ta"|"hi"}   change my language mid-session
    {"type":"mic", "on":true|false}
    {"type":"partial", "text": "..."}        live (interim) browser transcript
    {"type":"final", "text": "..."}          finished browser transcript
    {"type":"playback", "state":"start"|"end"}
    {"type":"interrupt"}
    {"type":"ping", "t": <client ms>}   /  {"type":"rtt", "ms": <number>}
client -> server (binary frames)
    16 kHz mono PCM16-LE microphone audio (server recognition mode only)

server -> client: hello, state, gate, status, transcript, translation, audio,
    speak, latency, dropped, notice, error, flush, pong, kicked
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import selftest
from .config import LANGUAGES, ROLE_LANG, ROOT_DIR, Settings, load_settings
from .loopguard import LoopGuard
from .netinfo import lan_ips
from .pipeline import Pipeline
from .session import ROLES, Device, Session, SessionManager
from .stt import build_server_stt, default_client_mode
from .translate import build_translator
from .tts import build_tts

log = logging.getLogger("interpreter.app")
STATIC_DIR = ROOT_DIR / "static"


def create_app(settings: Settings | None = None, *, translator=None, tts=None, server_stt="default",
               loopguard_factory=None) -> FastAPI:
    settings = settings or load_settings()
    translator = translator or build_translator(settings)
    tts = tts or build_tts(settings)
    if server_stt == "default":
        server_stt = build_server_stt(settings)
    pipeline = Pipeline(settings, translator, tts, server_stt)
    sessions = SessionManager(loopguard_factory or LoopGuard)

    app = FastAPI(title="AI Phone Interpreter", version="1.0")
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.pipeline = pipeline

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "sessions": len(sessions.sessions)}

    @app.get("/api/config")
    async def config():
        return {
            "providers": settings.public_view(),
            "translate_chain": [p.name for p in translator.providers],
            "tts_chain": [p.name for p in tts.providers],
            "server_stt_available": server_stt is not None,
            "default_stt_mode": default_client_mode(settings),
            "languages": LANGUAGES,
            "roles": ROLE_LANG,
            "lan_ips": lan_ips(),
            "https_port": settings.https_port,
            "http_port": settings.http_port,
        }

    @app.get("/api/new-session")
    async def new_session():
        code = sessions.new_code()
        while code in sessions.sessions:
            code = sessions.new_code()
        return {"session": code}

    @app.get("/api/sessions/{code}")
    async def session_state(code: str):
        s = sessions.sessions.get(sessions.clean_code(code))
        return s.state() if s else JSONResponse({"error": "no such session"}, status_code=404)

    @app.get("/api/selftest")
    async def run_selftest(diagnose: bool = False):
        return await selftest.run_all(settings, diagnose=diagnose)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, session: str = Query("demo"), role: str = Query("laptop"),
                          stt_mode: str = Query(""), lang: str = Query("")):
        await ws.accept()
        if role not in ROLES:
            await ws.send_text(json.dumps({"type": "error", "where": "connect", "message": f"bad role {role!r}"}))
            await ws.close(code=4400)
            return
        sess = sessions.get_or_create(session)
        mode = stt_mode if stt_mode in ("browser", "server") else default_client_mode(settings)
        device = Device(role=role, send_text=ws.send_text, stt_mode=mode,
                        lang=lang if lang in LANGUAGES else ROLE_LANG[role])
        old = sessions.attach(sess, device)
        if old is not None:
            await old.send({"type": "kicked", "message": f"Another {role} joined session {sess.id}."})
            old.closed = True
            if old.worker:
                old.worker.cancel()

        await device.send({
            "type": "hello", "session": sess.id, "role": role, "lang": device.lang,
            "peer_lang": (sess.peer_of(role).lang if sess.peer_of(role) else ROLE_LANG["phone" if role == "laptop" else "laptop"]),
            "stt_mode": device.stt_mode,
            "server_stt_available": server_stt is not None,
            "translate_chain": [p.name for p in translator.providers],
            "tts_chain": [p.name for p in tts.providers],
        })
        await sess.broadcast({"type": "state", **sess.state()})
        pipeline.ensure_worker(sess, device)

        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if device.closed:  # replaced by a newer connection
                    break
                if msg.get("bytes") is not None:
                    await _on_audio(sess, device, msg["bytes"])
                elif msg.get("text") is not None:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    await _on_message(sess, device, data)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("websocket error")
        finally:
            sessions.detach(sess, device)
            if sess.devices:
                await sess.broadcast({"type": "state", **sess.state()})
            try:
                await ws.close()
            except Exception:
                pass

    # ---------------------------------------------------------------- handlers
    async def _gate_broadcast(sess: Session, before: bool) -> None:
        now_closed = any(sess.loopguard.is_gated(r) for r in ROLES)
        if now_closed != before:
            await sess.broadcast({"type": "gate", "closed": now_closed})

    def _gated_any(sess: Session) -> bool:
        return any(sess.loopguard.is_gated(r) for r in ROLES)

    async def _on_audio(sess: Session, device: Device, pcm: bytes) -> None:
        if device.stt_mode != "server" or not device.mic_on:
            return
        if sess.loopguard.is_gated(device.role):
            if device.vad.in_speech:
                device.vad.reset()
                await sess.broadcast({"type": "status", "role": device.role, "state": "idle"})
            return
        for kind, payload in device.vad.feed(pcm):
            if kind == "start":
                await sess.broadcast({"type": "status", "role": device.role, "state": "speaking"})
            elif kind == "end":
                pipeline.submit_audio(sess, device, payload)
            elif kind == "discard":
                await sess.broadcast({"type": "status", "role": device.role, "state": "idle"})

    async def _on_message(sess: Session, device: Device, data: dict) -> None:
        t = data.get("type")
        guard = sess.loopguard
        if t == "partial":
            if not guard.is_gated(device.role):
                await sess.broadcast({"type": "transcript", "id": None, "role": device.role, "lang": device.lang,
                                      "final": False, "text": str(data.get("text", ""))[:1000]})
        elif t == "final":
            text = str(data.get("text", ""))[:2000].strip()
            if not text:
                return
            if guard.is_gated(device.role):
                await device.send({"type": "dropped", "role": device.role, "text": text,
                                   "reason": "audio was playing (feedback-loop guard)"})
                return
            await sess.broadcast({"type": "status", "role": device.role, "state": "translating"})
            pipeline.submit_text(sess, device, text)
        elif t == "playback":
            before = _gated_any(sess)
            if data.get("state") == "start":
                guard.playback_started(device.role)
            else:
                guard.playback_ended(device.role)
                # re-open after the tail so clients resume listening
                task = asyncio.create_task(_reopen_later(sess, guard.tail_s + 0.05))
                sess.tasks.add(task)
                task.add_done_callback(sess.tasks.discard)
            await sess.broadcast({"type": "status", "role": device.role,
                                  "state": "playing" if data.get("state") == "start" else "idle"})
            await _gate_broadcast(sess, before)
        elif t == "interrupt":
            sess.generation += 1
            guard.interrupt()
            for d in sess.devices.values():
                d.vad.reset()
            await sess.broadcast({"type": "flush", "by": device.role})
            await sess.broadcast({"type": "gate", "closed": False})
        elif t == "mic":
            device.mic_on = bool(data.get("on"))
            if not device.mic_on:
                for kind, payload in device.vad.flush():
                    if kind == "end" and device.stt_mode == "server":
                        pipeline.submit_audio(sess, device, payload)
            await sess.broadcast({"type": "state", **sess.state()})
        elif t == "lang":
            new = data.get("lang")
            if new in LANGUAGES:
                device.lang = new
                await sess.broadcast({"type": "state", **sess.state()})
        elif t == "mode":
            m = data.get("stt_mode")
            if m in ("browser", "server"):
                device.stt_mode = m
                device.vad.reset()
                await sess.broadcast({"type": "state", **sess.state()})
        elif t == "ping":
            await device.send({"type": "pong", "t": data.get("t")})
        elif t == "rtt":
            try:
                device.rtt_ms = round(float(data.get("ms")), 1)
            except (TypeError, ValueError):
                pass

    async def _reopen_later(sess: Session, delay: float) -> None:
        await asyncio.sleep(delay)
        if not _gated_any(sess):
            await sess.broadcast({"type": "gate", "closed": False})

    return app


def __getattr__(name: str):
    # Lazily build `app` so `uvicorn server.app:app` works without side effects on import.
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
