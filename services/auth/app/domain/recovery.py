"""Recovery codes for a lost phone (decision W22-5, W22-8). No I/O here.

Ten one-time codes of 10 base32 characters, written `XXXXX-XXXXX`. 50 bits each, so a plain
SHA-256 is enough to store them (a slow hash would only add a cost to the person using one). They
are shown once; only the hashes are kept.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any

COUNT = 10
_CHARS = 10


def _new_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(7)).decode()[:_CHARS]  # 56 bits in, 50 used
    return f"{raw[:5]}-{raw[5:]}"


def normalize(code: str) -> str:
    return "".join(code.split()).replace("-", "").upper()


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize(code).encode()).hexdigest()


def generate() -> tuple[list[str], list[dict[str, Any]]]:
    """The codes to show once, and the records to store (hash and `used_at`)."""
    codes = [_new_code() for _ in range(COUNT)]
    return codes, [{"hash": hash_code(c), "used_at": None} for c in codes]


def find_unused(records: list[dict[str, Any]], presented: str) -> str | None:
    """The stored hash of an unused code that matches, or None. Compares against every record."""
    wanted = hash_code(presented)
    found: str | None = None
    for record in records:
        if hmac.compare_digest(record["hash"], wanted) and record.get("used_at") is None:
            found = record["hash"]
    return found


def remaining(records: list[dict[str, Any]] | None) -> int:
    return sum(1 for r in records or [] if r.get("used_at") is None)
