"""Split translated text into sentence-sized chunks for TTS.

Synthesising the first sentence while the rest is still being generated cuts
the time until the listener hears something. Handles Latin and Indic
punctuation (। ॥) and avoids tiny fragments.
"""
from __future__ import annotations

import re

_SENT_END = re.compile(r"(?<=[.!?।॥])\s+")
_SOFT = re.compile(r"(?<=[,;:])\s+")


def split_sentences(text: str, min_chars: int = 12, max_chars: int = 180) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    parts = [p.strip() for p in _SENT_END.split(text) if p and p.strip()]

    # break very long sentences at commas
    pieces: list[str] = []
    for p in parts:
        if len(p) <= max_chars:
            pieces.append(p)
            continue
        cur = ""
        for sub in _SOFT.split(p):
            if cur and len(cur) + 1 + len(sub) > max_chars:
                pieces.append(cur)
                cur = sub
            else:
                cur = f"{cur} {sub}".strip()
        if cur:
            pieces.append(cur)

    # merge tiny fragments into their neighbour
    merged: list[str] = []
    for p in pieces:
        if merged and (len(merged[-1]) < min_chars or len(p) < min_chars) and len(merged[-1]) + len(p) < max_chars:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged
