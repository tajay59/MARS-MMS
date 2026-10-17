"""Signing keys (`signing_keys`, TRD §5.1, §6.1).

The private key is a file (a Docker secret); the database records its public half so JWKS
can keep publishing a key for a day after it is replaced, while tokens it signed expire.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from mms_common.auth.tokens import SigningKey
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]
PUBLISH_RETIRED_FOR = timedelta(days=1)


def load(path: str) -> SigningKey:
    key = load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path} is not an Ed25519 private key")
    return SigningKey(key)


async def activate(db: Db, key: SigningKey, ref: str, now: datetime) -> None:
    """Record `key` as the active one and retire any other. Safe to run in every worker."""
    col = db["signing_keys"]
    await col.update_one(
        {"_id": key.kid},
        {
            "$set": {"public_jwk": key.jwk, "private_key_ref": ref, "active": True},
            "$setOnInsert": {"created_at": now, "retired_at": None},
        },
        upsert=True,
    )
    await col.update_many(
        {"_id": {"$ne": key.kid}, "active": True},
        {"$set": {"active": False, "retired_at": now}},
    )


async def published(db: Db, now: datetime) -> list[dict[str, Any]]:
    """Active keys, and keys retired less than a day ago."""
    cursor = db["signing_keys"].find(
        {"$or": [{"active": True}, {"retired_at": {"$gt": now - PUBLISH_RETIRED_FOR}}]}
    )
    return [doc["public_jwk"] async for doc in cursor]
