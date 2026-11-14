"""The `client_reports` collection (TRD 5.2). A client reads their organization's submitted
reports and their own drafts; staff read submitted reports only, because a draft is the client's
private work (rules 3 and 6, filtered here so endpoint code can't forget)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User
from mms_common.errors import NotFound
from pymongo import DESCENDING
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.requests.requests import col as requests_col
from app.repo.stations.common import Db, Session, update_versioned


def col(db: Db) -> Any:
    return db["client_reports"]


def _visible(viewer: User, query: dict[str, Any]) -> dict[str, Any]:
    if viewer.is_client:
        own = viewer.org_id or object()
        return {"$and": [query, {"org_id": own, "$or": [
            {"status": "submitted"}, {"created_by": viewer.id},
        ]}]}
    return {"$and": [query, {"status": "submitted"}]}


async def get(
    db: Db, report_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """`viewer=None` is an internal read (the report service, the render consumer)."""
    query: dict[str, Any] = {"_id": report_id}
    if viewer is not None:
        query = _visible(viewer, query)
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, report_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any]:
    doc = await get(db, report_id, viewer, session)
    if doc is None:
        raise NotFound()
    return doc


async def search(
    db: Db, viewer: User, *, request_id: str | None, station_id: str | None, limit: int
) -> list[dict[str, Any]]:
    """Newest first (UUIDv7 IDs sort by creation time)."""
    query: dict[str, Any] = {}
    if request_id:
        query["request_id"] = request_id
    if station_id:
        query["station_ids"] = station_id
    cursor = col(db).find(_visible(viewer, query)).sort("_id", DESCENDING).limit(limit)
    return [d async for d in cursor]


async def counts(db: Db, request_ids: list[str], viewer: User) -> dict[str, int]:
    """Submitted reports per request, as this reader may see them."""
    rows = await col(db).aggregate([
        {"$match": _visible(viewer, {"request_id": {"$in": request_ids}})},
        {"$group": {"_id": "$request_id", "n": {"$sum": 1}}},
    ])
    return {row["_id"]: int(row["n"]) async for row in rows}


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db, report_id: str, changes: dict[str, Any], *, now: datetime, by: str | None,
    expected_version: int | None, session: AsyncClientSession,
) -> dict[str, Any]:
    return await update_versioned(
        col(db), report_id, changes, now=now, by=by, expected_version=expected_version,
        session=session,
    )


async def media_in_use(db: Db, media_id: str, report_id: str, session: Session = None) -> bool:
    """A file belongs to one thing, once: another report, a request or a comment holding it is
    a clash. The report that already holds it is not."""
    others = {"_id": {"$ne": report_id}}
    query = {"$or": [{"file.media_id": media_id}, {"form.images.media_id": media_id}], **others}
    if await col(db).find_one(query, {"_id": 1}, session=session):
        return True
    found = await requests_col(db).find_one({"attachments.media_id": media_id}, {"_id": 1},
                                            session=session)
    if found is not None:
        return True
    return bool(await db["comments"].find_one({"attachments.media_id": media_id}, {"_id": 1},
                                              session=session))
