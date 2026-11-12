"""TOTP secrets and recovery codes on the `users` record (decisions W22-4, W22-5).

`users.totp = {secret_enc, enabled_at, last_step}`; `users.recovery_codes = [{hash, used_at}]`;
`users.mfa_grace_until`. The secret is sealed with AES-GCM under `AUTH_TOTP_KEY` and bound to the
user's ID, so a copy of the database alone never gives a secret, and a sealed value moved to another
user's record does not open.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from mms_common.errors import AppError

from app.repo import users as users_repo

Db = users_repo.Db


class TotpUnavailable(AppError):
    status, code, title = 503, "totp_unavailable", "Two-step sign-in is not set up on this server"


def seal(key: bytes | None, secret: bytes, user_id: str) -> str:
    if key is None:
        raise TotpUnavailable()
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, secret, user_id.encode())).decode()


def unseal(key: bytes | None, sealed: str, user_id: str) -> bytes | None:
    """The secret, or None when the value was sealed under another key or for another user."""
    if key is None:
        raise TotpUnavailable()
    try:
        raw = base64.b64decode(sealed, validate=True)
        return AESGCM(key).decrypt(raw[:12], raw[12:], user_id.encode())
    except (InvalidTag, ValueError):
        return None


def enabled(user: dict[str, Any]) -> bool:
    return bool(user.get("totp"))


def enrolment_fields(
    sealed: str, recovery: list[dict[str, Any]], now: datetime, step: int
) -> dict[str, Any]:
    """`last_step` starts at the step of the confirming code, so that code can't be used again."""
    return {
        "totp": {"secret_enc": sealed, "enabled_at": now, "last_step": step},
        "recovery_codes": recovery,
        "mfa_grace_until": None,
    }


async def claim_step(db: Db, user_id: str, step: int) -> bool:
    """Record `step` as used. False when another request got there first: a replay."""
    result = await users_repo.col(db).update_one(
        {"_id": user_id, "totp.last_step": {"$lt": step}}, {"$set": {"totp.last_step": step}}
    )
    return bool(result.modified_count)


async def claim_recovery(db: Db, user_id: str, code_hash: str, now: datetime) -> bool:
    """Mark one recovery code used. False when it was already used (even a moment ago)."""
    result = await users_repo.col(db).update_one(
        {"_id": user_id, "recovery_codes": {"$elemMatch": {"hash": code_hash, "used_at": None}}},
        {"$set": {"recovery_codes.$.used_at": now}},
    )
    return bool(result.modified_count)
