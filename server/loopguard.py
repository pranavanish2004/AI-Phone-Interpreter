"""Feedback-loop prevention.

The danger: device B plays translated audio through its speaker, B's own mic
(or A's mic, when both devices sit in the same room) hears it, it gets
recognised and translated again -> endless ping-pong.

Three layers:
1. Half-duplex gate - while translated audio is playing, uploads from the gated
   devices are ignored. scope="session" (default) gates *both* devices, which
   is what you want when the laptop and phone are in the same room; scope="device"
   only gates the device that is playing (people in different rooms).
2. Tail - the gate stays closed for `tail_s` after playback ends (room echo).
3. Text echo check - a longer final transcript that arrives within a second of
   playback ending and closely matches what was just played is dropped.
The browser also mutes recognition locally while it plays (see static/app.js);
this module is the server-side safety net.
"""
from __future__ import annotations

import re
import time
import unicodedata
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) if min(len(a), len(b)) >= 4 else 0.0
    return SequenceMatcher(None, a, b).ratio()


class LoopGuard:
    def __init__(self, scope: str = "session", tail_s: float = 0.6, echo_window_s: float = 30.0,
                 echo_threshold: float = 0.85, echo_after_s: float = 1.0, max_play_s: float = 30.0,
                 clock=time.monotonic):
        assert scope in ("session", "device")
        self.scope = scope
        self.tail_s = tail_s
        self.echo_window_s = echo_window_s
        self.echo_after_s = echo_after_s
        self.echo_min_chars = 12
        self.echo_threshold = echo_threshold
        self.max_play_s = max_play_s           # safety: a lost "playback end" never blocks forever
        self.clock = clock
        self._playing_since: dict[str, float] = {}
        self._gate_until: dict[str, float] = {}
        self._recent: list[tuple[float, str]] = []

    # ----- playback reports from devices -----
    def playback_started(self, device: str) -> None:
        self._playing_since[device] = self.clock()

    def playback_ended(self, device: str) -> None:
        self._playing_since.pop(device, None)
        self._gate_until[device] = self.clock() + self.tail_s

    def interrupt(self) -> None:
        """User pressed interrupt: open every gate immediately."""
        self._playing_since.clear()
        self._gate_until.clear()

    def remember_played(self, text: str) -> None:
        now = self.clock()
        self._recent.append((now, text))
        self._recent = [(t, s) for t, s in self._recent if now - t <= self.echo_window_s]

    # ----- checks -----
    def _device_busy(self, device: str, now: float) -> bool:
        since = self._playing_since.get(device)
        if since is not None:
            if now - since <= self.max_play_s:
                return True
            self._playing_since.pop(device, None)
        return now < self._gate_until.get(device, 0.0)

    def is_gated(self, device: str) -> bool:
        now = self.clock()
        if self.scope == "device":
            return self._device_busy(device, now)
        devices = set(self._playing_since) | set(self._gate_until)
        return any(self._device_busy(d, now) for d in devices)

    def echo_reason(self, text: str) -> str | None:
        """Drop a transcript that repeats recently played audio *right after* playback.

        Only checked shortly after a playback finished (`echo_after_s`), so a
        person who deliberately replies with the same words a bit later
        (e.g. answering "namaskaram" with "namaskaram") is not blocked.
        """
        if len(normalize(text)) < self.echo_min_chars:
            return None   # short replies ("hello", "ok", "నమస్కారం") are never treated as echo
        now = self.clock()
        last_open = max(self._gate_until.values(), default=-1e9)
        recently_played = bool(self._playing_since) or now - last_open <= self.echo_after_s
        if not recently_played:
            return None
        for t, played in self._recent:
            if now - t <= self.echo_window_s and similarity(text, played) >= self.echo_threshold:
                return "echo of recently played audio"
        return None
