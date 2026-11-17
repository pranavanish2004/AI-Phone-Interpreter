"""Start the interpreter.

    python run.py

LOCAL mode (default) runs ONE app on two listeners:
    http://localhost:8000          -> open this on the laptop (localhost is allowed to use the mic)
    https://<laptop-ip>:8443       -> open this on the Android phone (mic needs HTTPS)
Both devices must be on the same Wi-Fi/hotspot.

CLOUD mode (--cloud, or the PORT environment variable is set - most hosting
platforms set this automatically) runs ONE plain-HTTP listener on that port.
The hosting platform terminates real HTTPS in front of it, so there is no
self-signed certificate and no same-network requirement: anyone with the
public URL can open it from anywhere. See README.md "Deploy for a demo".

Options:  --no-https   --http-port N   --https-port N   --host 0.0.0.0   --cloud
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    import uvicorn

    from scripts.gen_dev_cert import ensure_cert
    from server.app import create_app
    from server.config import load_settings

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Telugu text in Windows console logs
        except Exception:
            pass
    settings = load_settings()
    import os
    cloud_port = os.environ.get("PORT")  # most hosting platforms (Render, Railway, Fly...) set this
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--http-port", type=int, default=settings.http_port)
    ap.add_argument("--https-port", type=int, default=settings.https_port)
    ap.add_argument("--no-https", action="store_true")
    ap.add_argument("--cloud", action="store_true",
                    help="single plain-HTTP port; the hosting platform provides real HTTPS in front of it")
    args = ap.parse_args()
    cloud = args.cloud or cloud_port is not None

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(settings)

    if cloud:
        port = int(cloud_port or args.http_port)
        servers = [uvicorn.Server(uvicorn.Config(app, host=args.host, port=port, log_level="warning",
                                                 ws_ping_interval=20, ws_ping_timeout=20))]
        ips: list[str] = []
    else:
        servers = [uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.http_port, log_level="warning",
                                                 ws_ping_interval=20, ws_ping_timeout=20))]
        ips = []
        if not args.no_https:
            cert, key, ips = ensure_cert()
            servers.append(uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.https_port, log_level="warning",
                                                         ssl_certfile=str(cert), ssl_keyfile=str(key),
                                                         ws_ping_interval=20, ws_ping_timeout=20)))

    pv = settings.public_view()
    print("\n" + "=" * 64)
    print("  Telugu <-> English interpreter is running")
    print("=" * 64)
    if cloud:
        print(f"  Listening on 0.0.0.0:{servers[0].config.port} (plain HTTP; the platform adds real HTTPS)")
        print("  Open the public URL the host gives you - same link works for every device, anywhere.")
    else:
        print(f"  LAPTOP  : http://localhost:{args.http_port}")
        if not args.no_https:
            for ip in ips or ["<no LAN IP found - connect to Wi-Fi>"]:
                print(f"  PHONE   : https://{ip}:{args.https_port}")
    print("-" * 64)
    print(f"  Translation : {', '.join(p.name for p in app.state.pipeline.translator.providers)}")
    print(f"  Voice (TTS) : {', '.join(p.name for p in app.state.pipeline.tts.providers)}")
    stt = app.state.pipeline.server_stt
    print(f"  Recognition : browser (Chrome) by default; server STT = {stt.name if stt else 'not configured'}")
    print(f"  Azure speech key: {'yes' if pv['azure_speech_configured'] else 'no'} | "
          f"translator key: {'yes' if pv['azure_translator_configured'] else 'no'}")
    print("  Live provider check: open /api/selftest  or run  python scripts/stage1_probe.py")
    print("  Stop: Ctrl+C")
    print("=" * 64 + "\n", flush=True)

    async def serve_all():
        await asyncio.gather(*(s.serve() for s in servers))

    try:
        asyncio.run(serve_all())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
