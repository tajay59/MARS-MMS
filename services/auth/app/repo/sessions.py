"""Refresh-token families (`refresh_tokens`, TRD §5.1, §6.1). Only hashes are stored."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.ids import new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.tokens import seal_successor, token_hash

Db = AsyncDatabase[dict[str, Any]]
Session = AsyncClientSession | None


def col(db: Db) -> Any:
    return db["refresh_tokens"]


async def create(
    db: Db,
    *,
    user_id: str,
    raw: str,
    family_id: str,
    now: datetime,
    expires_at: datetime,
    device_label: str | None,
    session: AsyncClientSession,
) -> str:
    row_id = new_id()
    await col(db).insert_one(
        {
            "_id": row_id,
            "user_id": user_id,
            "token_hash": token_hash(raw),
            "family_id": family_id,
            "created_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
            "replaced_by": None,
            "rotated_at": None,
            "successor_enc": None,
            "device_label": device_label,
        },
        session=session,
    )
    return row_id


async def find(db: Db, raw: str, session: Session = None) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"token_hash": token_hash(raw)}, session=session
    )
    return doc


async def rotate(
    db: Db,
    row: dict[str, Any],
    presented: str,
    successor: str,
    *,
    now: datetime,
    expires_at: datetime,
    session: AsyncClientSession,
) -> bool:
    """Replace `row` with `successor` in one transaction. False when another request rotated
    it first (that request's transaction wins; this one takes the grace path)."""
    successor_id = new_id()
    result = await col(db).update_one(
        {"_id": row["_id"], "revoked_at": None},
        {
            "$set": {
                "revoked_at": now,
                "rotated_at": now,
                "replaced_by": successor_id,
                "successor_enc": seal_successor(presented, successor),
            }
        },
        session=session,
    )
    if result.modified_count != 1:
        return False
    await col(db).insert_one(
        {
            "_id": successor_id,
            "user_id": row["user_id"],
            "token_hash": token_hash(successor),
            "family_id": row["family_id"],
            "created_at": now,
            # Sliding: 30 days from the last refresh, which is also the PWA's offline_until.
            "expires_at": expires_at,
            "revoked_at": None,
            "replaced_by": None,
            "rotated_at": None,
            "successor_enc": None,
            "device_label": row.get("device_label"),
        },
        session=session,
    )
    return True


async def revoke_family(db: Db, family_id: str, now: datetime, session: Session = None) -> None:
    await col(db).update_many(
        {"family_id": family_id, "revoked_at": None},
        {"$set": {"revoked_at": now}},
        session=session,
    )


async def revoke_all(db: Db, now: datetime, *, session: Session = None) -> int:
    """End every open refresh session (an operator, after a restore). Returns how many were open."""
    result = await col(db).update_many({"revoked_at": None}, {"$set": {"revoked_at": now}},
                                       session=session)
    return int(result.modified_count)


async def revoke_users(
    db: Db,
    user_ids: list[str],
    now: datetime,
    *,
    keep_family: str | None = None,
    session: Session = None,
) -> None:
    """Log users out of every device (password reset, disabling, org deactivation)."""
    query: dict[str, Any] = {"user_id": {"$in": user_ids}, "revoked_at": None}
    if keep_family:
        query["family_id"] = {"$ne": keep_family}
    await col(db).update_many(query, {"$set": {"revoked_at": now}}, session=session)
