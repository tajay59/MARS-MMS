"""Opaque tokens: refresh, password reset and invitation (TRD §6.1, §6.2).

Each is 256 random bits, given to the browser once and stored only as a SHA-256 hash.

Refresh rotation has a 30-second grace window: a token rotated less than 30 s ago returns
the same successor instead of revoking the family, so two tabs or a tab and the service
worker refreshing together never log the user out. The successor is kept sealed under a
key derived from the token it replaced, so only a caller holding that token can open it, and
the database never holds a usable token.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _grace_key(presented: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"mms-refresh-grace"
    ).derive(presented.encode())


def seal_successor(presented: str, successor: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_grace_key(presented)).encrypt(nonce, successor.encode(), None)
    return base64.urlsafe_b64encode(nonce + sealed).decode()


def open_successor(presented: str, sealed: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(sealed.encode())
        return AESGCM(_grace_key(presented)).decrypt(raw[:12], raw[12:], None).decode()
    except (InvalidTag, ValueError):
        return None


class Refresh(StrEnum):
    ROTATE = "rotate"  # valid: issue a successor
    GRACE = "grace"  # rotated < 30 s ago: hand back the successor
    REUSE = "reuse"  # rotated longer ago: someone replayed it, revoke the family
    INVALID = "invalid"  # unknown, expired, or revoked by logout, reset or disabling


def decide(row: dict[str, Any] | None, now: datetime, grace: timedelta) -> Refresh:
    if row is None:
        return Refresh.INVALID
    if row.get("revoked_at") is None:
        return Refresh.ROTATE if row["expires_at"] > now else Refresh.INVALID
    rotated_at = row.get("rotated_at")
    if row.get("replaced_by") and rotated_at is not None:
        return Refresh.GRACE if now - rotated_at <= grace else Refresh.REUSE
    return Refresh.INVALID
