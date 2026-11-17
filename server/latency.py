"""Per-utterance latency measurement.

All timestamps are server-side `time.perf_counter()` so they are comparable.
What is measured (and shown in the UI):
    stt_ms        server STT time (azure mode; 0 in browser mode - the browser
                  recognises locally while the person is still talking)
    translate_ms  translation call
    tts_first_ms  time to synthesise the first sentence
    first_audio_ms  utterance received by server -> first audio/text sent to listener
The network hop to each phone/laptop is shown separately as ping RTT.
"""
from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class UtteranceTiming:
    t0: float = field(default_factory=time.perf_counter)
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, name: str) -> None:
        self.marks[name] = time.perf_counter()

    def span_ms(self, start: str | None, end: str) -> float:
        a = self.t0 if start is None else self.marks.get(start)
        b = self.marks.get(end)
        if a is None or b is None:
            return 0.0
        return round((b - a) * 1000, 1)

    def summary(self) -> dict:
        return {
            "stt_ms": self.span_ms(None, "stt_done") if "stt_done" in self.marks else 0.0,
            "translate_ms": self.span_ms("translate_start", "translate_done"),
            "tts_first_ms": self.span_ms("translate_done", "first_audio"),
            "first_audio_ms": self.span_ms(None, "first_audio"),
            "total_ms": self.span_ms(None, "done"),
        }


class LatencyStats:
    def __init__(self, window: int = 50):
        self.samples: deque[float] = deque(maxlen=window)

    def add(self, ms: float) -> None:
        if ms > 0:
            self.samples.append(ms)

    def snapshot(self) -> dict:
        if not self.samples:
            return {"count": 0, "median_ms": None, "p90_ms": None}
        s = sorted(self.samples)
        p90 = s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]
        return {"count": len(s), "median_ms": round(statistics.median(s), 1), "p90_ms": round(p90, 1)}
