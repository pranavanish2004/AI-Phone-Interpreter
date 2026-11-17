"""Live check of the REAL cloud services, using the keys in .env.

    python scripts/stage1_probe.py                 # everything
    python scripts/stage1_probe.py --translator-diagnose   # also try Azure Translator region variants
    python scripts/stage1_probe.py --json          # machine-readable

Checks (each is a real network call; keys are never printed):
  * translation en->te and te->en with: Azure Translator (if key), Google free, MyMemory
  * Azure TTS mp3 in Telugu + English (if speech key)
  * Azure STT round trip: Azure TTS -> 16 kHz WAV -> Azure STT, Telugu + English
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.config import load_settings  # noqa: E402
from server.selftest import run_all  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--translator-diagnose", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Telugu text on the Windows console
    except Exception:
        pass
    settings = load_settings()
    report = asyncio.run(run_all(settings, diagnose=a.translator_diagnose))
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("Settings:", json.dumps(report["settings"]))
    print("\n== Translation ==")
    for r in report["translation"]:
        mark = "OK  " if r["ok"] else "FAIL"
        detail = f"-> {r.get('output')}" if r["ok"] else f"-- {r.get('error')}"
        print(f"[{mark}] {r['check']:<18} {r['provider']:<12} {r['ms']:>5} ms {detail}")
    print("\n== Free server voices (Edge TTS / Google) ==")
    for r in report.get("voices", []):
        mark = "OK  " if r["ok"] else "FAIL"
        detail = f"{r.get('output')}" if r["ok"] else f"-- {r.get('error')}"
        print(f"[{mark}] {r['check']:<18} {r['provider']:<12} {r['ms']:>5} ms {detail}")
    print("\n== Azure Speech (STT/TTS) ==")
    for r in report["speech"]:
        mark = "OK  " if r["ok"] else "FAIL"
        extra = f" heard={r.get('output')!r} similarity={r.get('similarity')}" if "round trip" in r["check"] else \
            (f" {r.get('output')}" if r["ok"] else "")
        print(f"[{mark}] {r['check']:<20} {r['ms']:>5} ms{extra}{'' if r['ok'] else ' -- ' + str(r.get('error'))}")
    if "azure_translator_diagnosis" in report:
        print("\n== Azure Translator 401 diagnosis ==")
        for d in report["azure_translator_diagnosis"]:
            mark = "OK  " if d["ok"] else ("INFO" if d["ok"] is None else "FAIL")
            print(f"[{mark}] {d['variant']:<36} region={d.get('region_header')!s:<14} {d.get('error') or d.get('output') or ''}")
        win = [d for d in report["azure_translator_diagnosis"] if d["ok"]]
        if win:
            print(f"\n  ==> Put this in .env:  AZURE_TRANSLATOR_REGION={win[0]['region_header'] or ''}")
        else:
            print("\n  ==> No region variant worked: the key itself is wrong, or it is a Speech-only key."
                  "\n      Azure portal -> your *Translator* resource -> Keys and Endpoint -> copy KEY 1 and Location.")
    s = report["summary"]
    print("\n== Summary ==")
    print(f"  translation providers working : {', '.join(s['translation_working']) or 'NONE'}")
    print(f"  both directions translate     : {s['both_directions_translate']}")
    for lang, provs in s["server_voice_by_language"].items():
        print(f"  server voice for {lang}           : {', '.join(provs) or 'NONE (device voice will be used)'}")
    print(f"  Azure voice  te/en            : {s['azure_tts_te']}/{s['azure_tts_en']}")
    print(f"  Azure STT    te/en            : {s['azure_stt_te']}/{s['azure_stt_en']}  "
          f"(if False, use Browser recognition - the default)")
    return 0 if s["both_directions_translate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
