"""The `users` collection (TRD §5.1). Every write bumps `version` (optimistic concurrency and
the events' `aggregate_version`)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from mms_common.errors import NotFound, VersionConflict
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]
Session = AsyncClientSession | None


def col(db: Db) -> Any:
    return db["users"]


async def get(db: Db, user_id: str, session: Session = None) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"_id": user_id}, session=session)
    return doc


async def get_many(db: Db, user_ids: list[str]) -> list[dict[str, Any]]:
    """The users with these IDs that exist, in no particular order."""
    return [d async for d in col(db).find({"_id": {"$in": user_ids}})]


async def active_staff(db: Db, limit: int = 200) -> list[dict[str, Any]]:
    """Active technicians and admins, by name: who may attend a visit."""
    cursor = col(db).find(
        {"status": "active", "roles": {"$in": ["technician", "admin"]}}
    ).sort("name", 1).limit(limit)
    return [d async for d in cursor]


async def require(db: Db, user_id: str, session: Session = None) -> dict[str, Any]:
    doc = await get(db, user_id, session)
    if doc is None:
        raise NotFound()
    return doc


async def find_by_email(db: Db, email: str, session: Session = None) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one({"email": email}, session=session)
    return doc


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db,
    user_id: str,
    changes: dict[str, Any],
    *,
    now: datetime,
    by: str | None,
    session: AsyncClientSession,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Apply `changes` and bump `version`. With `expected_version`, a stale caller gets 409."""
    query: dict[str, Any] = {"_id": user_id}
    if expected_version is not None:
        query["version"] = expected_version
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        query,
        {"$set": {**changes, "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if doc is None:
        if expected_version is not None and await get(db, user_id, session) is not None:
            raise VersionConflict()
        raise NotFound()
    return doc


async def search(
    db: Db,
    *,
    status: str | None,
    role: str | None,
    org_id: str | None,
    q: str | None,
    after: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Admin list. Every filter is a typed value; `q` is escaped (CLAUDE.md rule 12)."""
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if role:
        query["roles"] = role
    if org_id:
        query["org_id"] = org_id
    if q:
        prefix = {"$regex": "^" + re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"email": prefix}, {"name": prefix}]
    if after:
        query["_id"] = {"$gt": after}
    cursor = col(db).find(query).sort("_id", 1).limit(limit)
    return [doc async for doc in cursor]


async def ids_in_org(db: Db, org_id: str, session: Session = None) -> list[str]:
    return [d["_id"] async for d in col(db).find({"org_id": org_id}, {"_id": 1}, session=session)]


async def stale_pending(db: Db, before: datetime) -> list[dict[str, Any]]:
    cursor = col(db).find({"status": "pending", "created_at": {"$lt": before}})
    return [doc async for doc in cursor]


async def delete_pending(db: Db, user_id: str, session: AsyncClientSession) -> bool:
    result = await col(db).delete_one({"_id": user_id, "status": "pending"}, session=session)
    return bool(result.deleted_count)
