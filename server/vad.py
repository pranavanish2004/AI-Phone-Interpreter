"""Energy-based voice activity detection / utterance segmentation.

Input: 16 kHz mono PCM16 little-endian, any chunk size.
Output events from `feed()`:
    ("start", None)          speech began
    ("end",   pcm_bytes)     utterance finished (includes ~300 ms pre-roll)
    ("discard", None)        a blip too short to be speech

Adaptive: tracks the background noise floor while nobody speaks, so it works
with laptop fans and phone noise suppression alike. Pure standard library.
"""
from __future__ import annotations

import math
from array import array
from collections import deque
from dataclasses import dataclass

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000      # 320
FRAME_BYTES = FRAME_SAMPLES * 2                      # 640


def frame_rms(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame[: len(frame) - (len(frame) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


@dataclass
class VADConfig:
    min_rms: float = 350.0          # absolute floor for "speech"
    noise_ratio: float = 2.8        # speech must be this many times louder than noise floor
    start_frames: int = 3           # 60 ms of speech to trigger start
    end_silence_ms: int = 700       # silence that closes an utterance
    preroll_ms: int = 300
    min_speech_ms: int = 250        # shorter bursts are discarded
    max_utterance_ms: int = 15000   # force-cut long monologues (Azure REST limit is 60 s)


class VADSegmenter:
    def __init__(self, cfg: VADConfig | None = None):
        self.cfg = cfg or VADConfig()
        self.noise_floor = 120.0
        self._buf = b""
        self._pre = deque(maxlen=max(1, self.cfg.preroll_ms // FRAME_MS))
        self._speech: list[bytes] = []
        self.in_speech = False
        self._voiced_run = 0
        self._silence_run = 0
        self._voiced_total = 0
        self.last_rms = 0.0

    @property
    def threshold(self) -> float:
        return max(self.cfg.min_rms, self.noise_floor * self.cfg.noise_ratio)

    def reset(self) -> None:
        self._buf = b""
        self._pre.clear()
        self._speech = []
        self.in_speech = False
        self._voiced_run = self._silence_run = self._voiced_total = 0

    def flush(self):
        """Close any open utterance (e.g. user turned the mic off)."""
        events = []
        if self.in_speech:
            events.append(self._finish())
        self.reset()
        return events

    def feed(self, pcm: bytes):
        events = []
        self._buf += pcm
        while len(self._buf) >= FRAME_BYTES:
            frame, self._buf = self._buf[:FRAME_BYTES], self._buf[FRAME_BYTES:]
            ev = self._process(frame)
            if ev:
                events.append(ev)
        return events

    def _finish(self):
        pcm = b"".join(self._speech)
        voiced_ms = self._voiced_total * FRAME_MS
        self._speech = []
        self.in_speech = False
        self._voiced_run = self._silence_run = self._voiced_total = 0
        if voiced_ms < self.cfg.min_speech_ms:
            return ("discard", None)
        return ("end", pcm)

    def _process(self, frame: bytes):
        rms = frame_rms(frame)
        self.last_rms = rms
        voiced = rms >= self.threshold
        if not self.in_speech:
            self._pre.append(frame)
            if voiced:
                self._voiced_run += 1
                if self._voiced_run >= self.cfg.start_frames:
                    self.in_speech = True
                    self._speech = list(self._pre)
                    self._pre.clear()
                    self._voiced_total = self._voiced_run
                    self._silence_run = 0
                    return ("start", None)
            else:
                self._voiced_run = 0
                # adapt the noise floor only while nobody is talking
                self.noise_floor = 0.95 * self.noise_floor + 0.05 * max(rms, 1.0)
            return None

        self._speech.append(frame)
        if voiced:
            self._voiced_total += 1
            self._silence_run = 0
        else:
            self._silence_run += 1
        if self._silence_run * FRAME_MS >= self.cfg.end_silence_ms:
            # drop most of the trailing silence
            keep = max(0, len(self._speech) - self._silence_run + 5)
            self._speech = self._speech[:keep]
            return self._finish()
        if len(self._speech) * FRAME_MS >= self.cfg.max_utterance_ms:
            return self._finish()
        return None
