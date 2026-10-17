"""auth indexes (TRD §5.1, BSD "auth")."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

HAS_TOKEN = {"token_hash": {"$type": "string"}}


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    users = db["users"]
    await users.create_index("email", unique=True)
    await users.create_index("status")
    await users.create_index("org_id")
    await users.create_index([("status", ASCENDING), ("created_at", ASCENDING)])

    await db["organizations"].create_index("name_key", unique=True)

    refresh = db["refresh_tokens"]
    await refresh.create_index("token_hash", unique=True)
    await refresh.create_index("family_id")
    await refresh.create_index("user_id")
    await refresh.create_index("expires_at", expireAfterSeconds=0)

    for name in ("password_resets", "invitations"):
        links = db[name]
        # Rows wait without a token until notification mints one, so only real hashes count.
        await links.create_index(
            "token_hash", unique=True, partialFilterExpression=HAS_TOKEN
        )
        await links.create_index("user_id")
        await links.create_index("expires_at", expireAfterSeconds=0)
