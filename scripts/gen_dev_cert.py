"""Create a self-signed HTTPS certificate for this laptop's LAN address(es).

Android Chrome only allows the microphone on https:// (or localhost), so the
phone must open https://<laptop-ip>:8443. The certificate is valid for
localhost, 127.0.0.1 and every current LAN IPv4 address. It is regenerated
automatically by run.py when the laptop's IP changes.

Usage:  python scripts/gen_dev_cert.py [--force] [--ip 192.168.1.20 ...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.netinfo import lan_ips  # noqa: E402

CERT_DIR = ROOT / "certs"
CERT = CERT_DIR / "dev-cert.pem"
KEY = CERT_DIR / "dev-key.pem"
META = CERT_DIR / "dev-cert.json"


def cert_covers(ips: list[str]) -> bool:
    if not (CERT.exists() and KEY.exists() and META.exists()):
        return False
    try:
        meta = json.loads(META.read_text())
        not_after = dt.datetime.fromisoformat(meta["not_after"])
        return set(ips) <= set(meta["ips"]) and not_after > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    except Exception:
        return False


def generate(ips: list[str]) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CERT_DIR.mkdir(exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AI Interpreter local dev")])
    all_ips = sorted(set(ips) | {"127.0.0.1"})
    san = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in all_ips]
    now = dt.datetime.now(dt.timezone.utc)
    not_after = now + dt.timedelta(days=397)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    META.write_text(json.dumps({"ips": all_ips, "not_after": not_after.isoformat()}, indent=2))


def ensure_cert(extra_ips: list[str] | None = None, force: bool = False) -> tuple[Path, Path, list[str]]:
    ips = sorted(set(lan_ips()) | set(extra_ips or []))
    if force or not cert_covers(ips):
        generate(ips)
        print(f"[cert] generated self-signed certificate for: localhost, {', '.join(ips) or '(no LAN IP)'}")
    return CERT, KEY, ips


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--ip", action="append", default=[])
    a = ap.parse_args()
    c, k, ips = ensure_cert(a.ip, a.force)
    print(f"certificate: {c}\nkey:         {k}\nLAN IPs:     {', '.join(ips) or 'none found'}")
