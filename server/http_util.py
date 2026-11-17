"""Tiny async HTTP helper on top of the standard library (no extra deps).

Requests run in a worker thread so they never block the event loop.
"""
from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class ProviderError(Exception):
    """A cloud provider call failed. `status` is the HTTP status (0 = network)."""

    def __init__(self, provider: str, message: str, status: int = 0, code: str | None = None):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status
        self.code = code
        self.message = message


@dataclass
class HttpResponse:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


_SSL_CTX = ssl.create_default_context()


def _do_request(method: str, url: str, headers: dict, data: bytes | None, timeout: float) -> HttpResponse:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        ctx = _SSL_CTX if url.startswith("https") else None
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return HttpResponse(resp.status, dict(resp.headers), resp.read())
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return HttpResponse(e.code, dict(e.headers or {}), body)


async def request(method: str, url: str, *, provider: str, headers: dict | None = None,
                  data: bytes | None = None, params: dict | None = None,
                  timeout: float = 10.0) -> HttpResponse:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    try:
        return await asyncio.to_thread(_do_request, method, url, headers or {}, data, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ProviderError(provider, f"network error: {reason}") from None


def short(text: str, n: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "..."
