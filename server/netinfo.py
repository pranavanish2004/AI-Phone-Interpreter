"""Find this computer's local-network IPv4 addresses (for the phone URL)."""
from __future__ import annotations

import socket


def lan_ips() -> list[str]:
    ips: list[str] = []
    # The UDP "connect" trick sends no packets; it just asks the OS which
    # interface would be used for the default route.
    for probe in ("8.8.8.8", "10.255.255.255", "192.168.255.255"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 80))
                ip = s.getsockname()[0]
                if ip not in ips and not ip.startswith("127."):
                    ips.append(ip)
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith(("127.", "169.254.")):
                ips.append(ip)
    except OSError:
        pass
    return ips
