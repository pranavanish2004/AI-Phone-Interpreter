"""Conversation sessions ("rooms").

A session has two seats, "laptop" and "phone". Each person picks their own
language when joining (default: laptop English, phone Telugu); whatever one
person says is translated into the other person's language. Each connected device gets a `Device` with its own
send lock, VAD segmenter (for server-side STT) and an ordered work queue so
utterances from one speaker are translated and played in order.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .config import LANGUAGES, ROLE_LANG
from .latency import LatencyStats
from .loopguard import LoopGuard
from .vad import VADSegmenter

log = logging.getLogger("interpreter.session")

ROLES = ("laptop", "phone")
SendFn = Callable[[str], Awaitable[None]]


def other_role(role: str) -> str:
    return "phone" if role == "laptop" else "laptop"


@dataclass
class Device:
    role: str
    send_text: SendFn
    stt_mode: str = "browser"                   # browser | server
    lang: str = ""
    connected_at: float = field(default_factory=time.time)
    rtt_ms: float | None = None
    mic_on: bool = False
    vad: VADSegmenter = field(default_factory=VADSegmenter)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    worker: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: bool = False

    def __post_init__(self):
        if not self.lang:
            self.lang = ROLE_LANG[self.role]

    async def send(self, msg: dict) -> bool:
        if self.closed:
            return False
        try:
            async with self._lock:
                await self.send_text(json.dumps(msg, ensure_ascii=False))
            return True
        except Exception as e:  # socket gone
            log.info("send to %s failed: %s", self.role, e)
            self.closed = True
            return False

    def info(self) -> dict:
        return {"role": self.role, "lang": self.lang, "lang_name": LANGUAGES[self.lang]["name"],
                "lang_native": LANGUAGES[self.lang]["native"],
                "stt_mode": self.stt_mode, "mic_on": self.mic_on, "rtt_ms": self.rtt_ms}


@dataclass
class Session:
    id: str
    devices: dict[str, Device] = field(default_factory=dict)
    loopguard: LoopGuard = field(default_factory=LoopGuard)
    # keyed by speaker->listener seat, e.g. "phone->laptop" (languages can be anything)
    latency: dict[str, LatencyStats] = field(default_factory=lambda: {"phone->laptop": LatencyStats(),
                                                                      "laptop->phone": LatencyStats()})
    created_at: float = field(default_factory=time.time)
    generation: int = 0                          # bumped on interrupt; stale audio is dropped
    _seq: int = 0
    tasks: set = field(default_factory=set)

    def next_utterance_id(self, role: str) -> str:
        self._seq += 1
        return f"{role[0]}{self._seq}"

    def peer_of(self, role: str) -> Device | None:
        d = self.devices.get(other_role(role))
        return d if d and not d.closed else None

    async def broadcast(self, msg: dict) -> None:
        await asyncio.gather(*(d.send(msg) for d in list(self.devices.values())), return_exceptions=True)

    def state(self) -> dict:
        return {
            "session": self.id,
            "devices": {r: (d.info() if d and not d.closed else None) for r in ROLES for d in [self.devices.get(r)]},
            "latency": {k: v.snapshot() for k, v in self.latency.items()},
        }


class SessionManager:
    def __init__(self, loopguard_factory: Callable[[], LoopGuard] = LoopGuard):
        self.sessions: dict[str, Session] = {}
        self.loopguard_factory = loopguard_factory

    @staticmethod
    def new_code() -> str:
        return f"{secrets.randbelow(9000) + 1000}"

    @staticmethod
    def clean_code(code: str) -> str:
        code = "".join(ch for ch in code if ch.isalnum() or ch in "-_")[:32]
        return code or "demo"

    def get_or_create(self, code: str) -> Session:
        code = self.clean_code(code)
        s = self.sessions.get(code)
        if s is None:
            s = Session(id=code, loopguard=self.loopguard_factory())
            self.sessions[code] = s
        return s

    def attach(self, session: Session, device: Device) -> Device | None:
        """Add device; returns the previous device with the same role (to be kicked)."""
        old = session.devices.get(device.role)
        session.devices[device.role] = device
        return old

    def detach(self, session: Session, device: Device) -> None:
        device.closed = True
        if session.devices.get(device.role) is device:
            del session.devices[device.role]
        if device.worker:
            device.worker.cancel()
        if not session.devices:
            for t in list(session.tasks):
                t.cancel()
            self.sessions.pop(session.id, None)
