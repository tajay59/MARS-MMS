"""The `notifications` collection: one row per person per event (PRD NOT-1, NOT-2). Everything
is scoped to the caller's own `user_id` here, so a route can't read someone else's list (rule 3).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from mms_common.ids import new_id
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.notifications import Draft

Db = AsyncDatabase[dict[str, Any]]
KEEP = timedelta(days=365)


def col(db: Db) -> Any:
    return db["notifications"]


async def ensure_indexes(db: Db) -> None:
    c = col(db)
    await c.create_index([("user_id", ASCENDING), ("_id", DESCENDING)])
    # One notification per person per event: a redelivered event can't write a second
    await c.create_index([("user_id", ASCENDING), ("event_id", ASCENDING), ("type", ASCENDING)],
                         unique=True)
    await c.create_index([("user_id", ASCENDING), ("read_at", ASCENDING)])
    await c.create_index("created_at", expireAfterSeconds=int(KEEP.total_seconds()))
    users = db["user_directory"]
    await users.create_index([("status", ASCENDING), ("roles", ASCENDING)])
    await users.create_index([("org_id", ASCENDING), ("status", ASCENDING)], sparse=True)


async def insert_many(
    db: Db, drafts: list[Draft], event_id: str, now: datetime, session: AsyncClientSession
) -> list[dict[str, Any]]:
    docs = [
        {
            "_id": new_id(), "user_id": d.user_id, "type": d.type, "title": d.title,
            "body": d.body, "link": d.link,
            "entity": {"type": d.entity_type, "id": d.entity_id},
            "event_id": event_id, "read_at": None, "created_at": now,
        }
        for d in drafts
    ]
    if docs:
        await col(db).insert_many(docs, session=session)
    return docs


async def page(
    db: Db, user_id: str, *, before: str | None, after: str | None, unread: bool,
    type_prefix: str | None, limit: int,
) -> list[dict[str, Any]]:
    """Newest first. `after` is catch-up (everything newer than that ID); `before` pages back."""
    query: dict[str, Any] = {"user_id": user_id}
    if unread:
        query["read_at"] = None
    if type_prefix:
        query["type"] = {"$regex": f"^{type_prefix}"}  # typed values only (rule 12)
    if after:
        query["_id"] = {"$gt": after}
    elif before:
        query["_id"] = {"$lt": before}
    cursor = col(db).find(query).sort("_id", DESCENDING).limit(limit)
    return [d async for d in cursor]


async def unread_count(db: Db, user_id: str) -> int:
    return int(await col(db).count_documents({"user_id": user_id, "read_at": None}))


async def mark_read(db: Db, user_id: str, notification_id: str, now: datetime) -> bool:
    result = await col(db).update_one(
        {"_id": notification_id, "user_id": user_id, "read_at": None}, {"$set": {"read_at": now}}
    )
    if result.modified_count:
        return True
    # Already read counts as done; someone else's, or none, does not
    return bool(await col(db).count_documents({"_id": notification_id, "user_id": user_id}) == 1)


async def mark_all_read(db: Db, user_id: str, now: datetime) -> int:
    result = await col(db).update_many({"user_id": user_id, "read_at": None},
                                       {"$set": {"read_at": now}})
    return int(result.modified_count)
