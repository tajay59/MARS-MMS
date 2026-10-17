"""Single-use emailed links: `password_resets` and `invitations` (TRD §5.1, §6.2).

A row is created when the reset is requested or the user invited, with no token yet. The
token is minted only when platform's notification module asks for the link to email it
(`/internal/account-links`), so no token ever passes through an event. Minting again
replaces the earlier token, so only the newest link works.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from mms_common.ids import new_id
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.tokens import new_token, token_hash

Db = AsyncDatabase[dict[str, Any]]


class Kind(StrEnum):
    RESET = "reset"
    INVITATION = "invitation"


COLLECTION = {Kind.RESET: "password_resets", Kind.INVITATION: "invitations"}


def col(db: Db, kind: Kind) -> Any:
    return db[COLLECTION[kind]]


async def create(
    db: Db, kind: Kind, user_id: str, *, now: datetime, expires_at: datetime,
    session: AsyncClientSession,
) -> str:
    """A new link row. Earlier unused links of the same kind for the user stop working."""
    await col(db, kind).update_many(
        {"user_id": user_id, "used_at": None},
        {"$set": {"used_at": now, "superseded": True}},
        session=session,
    )
    link_id = new_id()
    await col(db, kind).insert_one(
        {
            "_id": link_id,
            "user_id": user_id,
            "token_hash": None,
            "created_at": now,
            "expires_at": expires_at,
            "used_at": None,
        },
        session=session,
    )
    return link_id


async def mint(
    db: Db, kind: Kind, link_id: str, now: datetime
) -> tuple[str, dict[str, Any]] | None:
    """A fresh token for a link that is still open, or None."""
    raw = new_token()
    row: dict[str, Any] | None = await col(db, kind).find_one_and_update(
        {"_id": link_id, "used_at": None, "expires_at": {"$gt": now}},
        {"$set": {"token_hash": token_hash(raw), "minted_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    return (raw, row) if row else None


async def find_open(db: Db, kind: Kind, raw: str, now: datetime) -> dict[str, Any] | None:
    row: dict[str, Any] | None = await col(db, kind).find_one(
        {"token_hash": token_hash(raw), "used_at": None, "expires_at": {"$gt": now}}
    )
    return row


async def use(
    db: Db, kind: Kind, link_id: str, now: datetime, session: AsyncClientSession
) -> bool:
    result = await col(db, kind).update_one(
        {"_id": link_id, "used_at": None}, {"$set": {"used_at": now}}, session=session
    )
    return bool(result.modified_count)
