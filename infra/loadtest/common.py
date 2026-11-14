"""What the load test files share (W20 slice 6): where the target is, who signs in, device-made ids.

No Locust import here, so `seed_volume.py` and the threshold check can use it too.

    LOAD_URL        the site, default https://mms.localhost
    LOAD_CONNECT    an address to connect to instead of resolving LOAD_URL's host (the local stack
                    answers on 127.0.0.1 and a hosts-file entry is not needed); the Host header
                    and the TLS server name stay the site's
    LOAD_PASSWORD   the seed users' password (AUTH_SEED_PASSWORD), default the local one
"""

from __future__ import annotations

import os
import secrets
import time
from urllib.parse import urlsplit

URL = os.environ.get("LOAD_URL", "https://mms.localhost").rstrip("/")
CONNECT = os.environ.get("LOAD_CONNECT", "")
PASSWORD = os.environ.get("LOAD_PASSWORD", "dev-seed-password-1")
HOST = urlsplit(URL).hostname or "mms.localhost"
SCHEME = urlsplit(URL).scheme or "https"

ORG_A = "01900000-0000-7000-8000-00000000a000"
ORG_B = "01900000-0000-7000-8000-00000000b000"

# The seed users of mms_common.testing.seed, by the role they play in the mix
EMAILS = {
    "admin": "admin@example.org",
    "viewer": "viewer@example.org",
    "tech1": "tech1@example.org",
    "tech2": "tech2@example.org",
    "client_a1": "client.a1@example.org",
    "client_a2": "client.a2@example.org",
    "client_b1": "client.b1@example.org",
}


def base_url() -> str:
    """Where requests go: the site, or the address in LOAD_CONNECT with the site's Host header."""
    return f"{SCHEME}://{CONNECT}" if CONNECT else URL


def host_header() -> dict[str, str]:
    return {"Host": HOST} if CONNECT else {}


def files_url(url: str) -> tuple[str, dict[str, str]]:
    """A presigned URL names the files host; connect where LOAD_CONNECT says and keep the name in
    the Host header, which is what the signature covers."""
    parts = urlsplit(url)
    if not CONNECT:
        return url, {}
    return f"{parts.scheme}://{CONNECT}{parts.path}?{parts.query}", {
        "Host": parts.netloc
    }


def uuid7() -> str:
    """A UUIDv7 for a device-made id (rule 9)."""
    ms = int(time.time() * 1000)
    rand = secrets.randbits(74)
    value = (
        (ms << 80)
        | (0x7 << 76)
        | ((rand >> 62) << 64)
        | (0b10 << 62)
        | (rand & (2**62 - 1))
    )
    h = f"{value:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
