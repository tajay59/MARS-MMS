"""The `organizations` collection (TRD §5.1). A client reads only their own (rule 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from mms_common.errors import NotFound, VersionConflict
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]
Session = AsyncClientSession | None


def col(db: Db) -> Any:
    return db["organizations"]


async def get(
    db: Db, org_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """`viewer=None` is an internal read; a client viewer sees only their own org."""
    query: dict[str, Any] = {"_id": org_id}
    if viewer is not None:
        query = scoped(viewer, query, "_id")
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, org_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any]:
    doc = await get(db, org_id, viewer, session)
    if doc is None:
        raise NotFound()
    return doc


async def search(
    db: Db, viewer: User, *, status: str | None, after: str | None, limit: int
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if after:
        query["_id"] = {"$gt": after}
    cursor = col(db).find(scoped(viewer, query, "_id")).sort("name_key", 1).limit(limit)
    return [doc async for doc in cursor]


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db,
    org_id: str,
    changes: dict[str, Any],
    *,
    now: datetime,
    by: str,
    expected_version: int,
    session: AsyncClientSession,
) -> dict[str, Any]:
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": org_id, "version": expected_version},
        {"$set": {**changes, "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if doc is None:
        if await get(db, org_id, session=session) is not None:
            raise VersionConflict()
        raise NotFound()
    return doc


async def known_keys(db: Db) -> tuple[set[str], set[str]]:
    """Every external ID and name key in use, for the organization import (W5-8)."""
    ids: set[str] = set()
    names: set[str] = set()
    async for doc in col(db).find({}, {"external_id": 1, "name_key": 1}):
        if doc.get("external_id"):
            ids.add(doc["external_id"])
        names.add(doc["name_key"])
    return ids, names
