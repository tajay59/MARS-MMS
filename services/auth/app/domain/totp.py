"""Time-based one-time passwords (RFC 6238; decision W22-3). No I/O here.

HMAC-SHA1, 6 digits and a 30-second step: what every authenticator app supports. A code is
accepted one step either side of now (clock drift), and never twice: the caller stores the last
accepted step and passes it back as `last_step`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote, urlencode

STEP_S = 30
DIGITS = 6
SECRET_BYTES = 20  # 160 bits, the size RFC 4226 recommends
WINDOW = 1  # steps accepted either side of now


def new_secret() -> bytes:
    return secrets.token_bytes(SECRET_BYTES)


def to_base32(secret: bytes) -> str:
    """What the person types when they can't scan the QR code (no padding: 32 characters)."""
    return base64.b32encode(secret).decode().rstrip("=")


def from_base32(text: str) -> bytes:
    cleaned = "".join(text.split()).upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def hotp(secret: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 §5.3: dynamic truncation of HMAC-SHA1."""
    mac = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()  # noqa: S324 - RFC 6238
    offset = mac[-1] & 0x0F
    number = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**digits).zfill(digits)


def step_at(now_s: float) -> int:
    return int(now_s // STEP_S)


def code_at(secret: bytes, now_s: float, digits: int = DIGITS) -> str:
    return hotp(secret, step_at(now_s), digits)


def clean_code(code: str) -> str | None:
    """The six digits, or None. Phones' keyboards offer the code with a space in the middle."""
    digits = "".join(code.split())
    return digits if len(digits) == DIGITS and digits.isascii() and digits.isdigit() else None


def verify(secret: bytes, code: str, now_s: float, last_step: int | None) -> int | None:
    """The step the code belongs to, or None. A step at or before `last_step` is a replay.

    Every step in the window is compared, so how long it takes does not say which step (or how
    many digits) matched."""
    cleaned = clean_code(code)
    if cleaned is None:
        return None
    current = step_at(now_s)
    matched: int | None = None
    for step in range(current - WINDOW, current + WINDOW + 1):
        if hmac.compare_digest(hotp(secret, step), cleaned) and (
            last_step is None or step > last_step
        ):
            matched = step
    return matched


def otpauth_uri(secret: bytes, account: str, issuer: str) -> str:
    """The `otpauth://` address that authenticator apps read from a QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode(
        {"secret": to_base32(secret), "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS,
         "period": STEP_S},
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{query}"
