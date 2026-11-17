"""Shared fixtures.

`fake_cloud` runs a local HTTP server that imitates the *real* REST contracts
of Azure Translator, Azure Speech STT/TTS, Google gtx and MyMemory (paths,
headers, status codes, JSON shapes). It lets the real provider classes be
exercised end-to-end without internet or keys.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.config import Settings  # noqa: E402

GOOD_KEY = "good-key-123"
GOOD_SPEECH_KEY = "speech-key-456"
REGION = "centralindia"


def _wav(seconds=0.3, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeCloud(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *a):
        pass

    def _send(self, status, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        FakeCloud.calls.append(("GET", u.path, dict(self.headers), q))
        if u.path == "/gtx":
            text = q["q"][0]
            if text == "FAIL":
                return self._send(429, b"Too Many Requests", "text/plain")
            return self._send(200, [[[f"G[{q['tl'][0]}]:{text}", text, None, None]], None, q["sl"][0]])
        if u.path == "/gtts":
            text = q["q"][0]
            if text == "FAIL":
                return self._send(200, b"<html>unusual traffic</html>", "text/html")
            assert q["client"] == ["tw-ob"] and len(text) <= 200
            return self._send(200, b"ID3" + f"[{q['tl'][0]}:{q['idx'][0]}/{q['total'][0]}]".encode() + b"\x00" * 50,
                              "audio/mpeg")
        if u.path == "/mm":
            text = q["q"][0]
            return self._send(200, {"responseData": {"translatedText": f"M[{q['langpair'][0]}]:{text}"},
                                    "responseStatus": 200})
        self._send(404, {"error": "nope"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        FakeCloud.calls.append(("POST", u.path, dict(self.headers), q, body))
        if u.path == "/translate":
            if self.headers.get("Ocp-Apim-Subscription-Key") != GOOD_KEY or \
                    self.headers.get("Ocp-Apim-Subscription-Region") != REGION:
                return self._send(401, {"error": {"code": 401001, "message": "The request is not authorized "
                                                  "because credentials are missing or invalid."}})
            assert q["api-version"] == ["3.0"]
            items = json.loads(body)
            return self._send(200, [{"translations": [{"text": f"AZ[{q['to'][0]}]:{items[0]['Text']}",
                                                       "to": q["to"][0]}]}])
        if u.path == "/stt":
            if self.headers.get("Ocp-Apim-Subscription-Key") != GOOD_SPEECH_KEY:
                return self._send(401, b"", "text/plain")
            assert self.headers["Content-Type"].startswith("audio/wav")
            assert body[:4] == b"RIFF"
            lang = q["language"][0]
            if len(body) < 1000:
                return self._send(200, {"RecognitionStatus": "NoMatch"})
            return self._send(200, {"RecognitionStatus": "Success", "DisplayText": f"heard {lang}"})
        if u.path == "/tts":
            if self.headers.get("Ocp-Apim-Subscription-Key") != GOOD_SPEECH_KEY:
                return self._send(401, b"", "text/plain")
            ssml = body.decode()
            assert "<voice" in ssml
            fmt = self.headers["X-Microsoft-OutputFormat"]
            if fmt.startswith("riff"):
                return self._send(200, _wav(0.5), "audio/wav")
            return self._send(200, b"ID3" + b"\x00" * 200, "audio/mpeg")
        self._send(404, {"error": "nope"})


@pytest.fixture(scope="session")
def fake_cloud():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeCloud)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def cloud_settings(fake_cloud):
    def make(**overrides) -> Settings:
        base = dict(
            azure_translator_key=GOOD_KEY, azure_translator_region=REGION,
            azure_translator_endpoint=fake_cloud,
            azure_speech_key=GOOD_SPEECH_KEY, azure_speech_region=REGION,
            azure_speech_endpoint_stt=f"{fake_cloud}/stt", azure_speech_endpoint_tts=f"{fake_cloud}/tts",
            google_free_endpoint=f"{fake_cloud}/gtx", mymemory_endpoint=f"{fake_cloud}/mm",
            google_tts_endpoint=f"{fake_cloud}/gtts",
            provider_timeout_s=5.0,
        )
        base.update(overrides)
        return Settings(**base)
    return make
