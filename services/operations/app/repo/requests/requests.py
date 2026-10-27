"""The `requests` and `counters` collections. A client reads only their organization's
requests (rule 3, scoped on `org_id`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from mms_common.errors import Conflict, NotFound, VersionConflict
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.requests import rules
from app.repo.stations.common import Db, Session, contains


def col(db: Db) -> Any:
    return db["requests"]


@dataclass(frozen=True)
class Filters:
    statuses: tuple[str, ...] = ()
    org_id: str | None = None
    station_ids: tuple[str, ...] | None = None  # already narrowed by country or station
    category: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    q: str | None = None
    unassigned: bool = False


def _query(viewer: User, f: Filters) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if f.statuses:
        query["status"] = {"$in": list(f.statuses)}
    if f.org_id:
        query["org_id"] = f.org_id
    if f.station_ids is not None:
        query["station_ids"] = {"$in": list(f.station_ids)}
    if f.category:
        query["category"] = f.category
    if f.priority:
        query["priority"] = f.priority
    if f.assigned_to:
        query["assigned_staff_ids"] = f.assigned_to
    elif f.unassigned:
        query["assigned_staff_ids"] = []
    if f.created_from or f.created_to:
        window: dict[str, datetime] = {}
        if f.created_from:
            window["$gte"] = f.created_from
        if f.created_to:
            window["$lt"] = f.created_to
        query["created_at"] = window
    if f.q:
        query["$or"] = [{"ref": contains(f.q)}, {"title": contains(f.q)}]
    return scoped(viewer, query)


async def search(
    db: Db, viewer: User, f: Filters, *, after: str | None, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """Newest first (UUIDv7 IDs sort by creation time), after the ID `after`, and the total
    that match."""
    query = _query(viewer, f)
    total = int(await col(db).count_documents(query))
    if after:
        query = {"$and": [query, {"_id": {"$lt": after}}]}
    cursor = col(db).find(query).sort("_id", -1).limit(limit)
    return [d async for d in cursor], total


async def queue(
    db: Db, viewer: User, f: Filters, *, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """The approved requests nobody has taken, oldest approval first (REQ-7, AFD `/queue`),
    and how many there are."""
    query = _query(viewer, f)
    total = int(await col(db).count_documents(query))
    cursor = col(db).find(query).sort([("milestones.approved_at", 1), ("_id", 1)]).limit(limit)
    return [d async for d in cursor], total


# From assignment to closure a request counts as someone's work (REOPENED returns at once).
OPEN_STATUSES = ("assigned", "scheduled", "in_progress", "client_review", "reopened")


async def workload(db: Db) -> dict[str, int]:
    """Open requests per assigned person, for the Assign dialog."""
    rows = await col(db).aggregate([
        {"$match": {"status": {"$in": list(OPEN_STATUSES)}}},
        {"$unwind": "$assigned_staff_ids"},
        {"$group": {"_id": "$assigned_staff_ids", "n": {"$sum": 1}}},
    ])
    return {row["_id"]: int(row["n"]) async for row in rows}


async def get(
    db: Db, request_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """`viewer=None` is an internal read."""
    query: dict[str, Any] = {"_id": request_id}
    if viewer is not None:
        query = scoped(viewer, query)
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, request_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any]:
    doc = await get(db, request_id, viewer, session)
    if doc is None:
        raise NotFound()
    return doc


async def next_ref(db: Db, now: datetime, session: AsyncClientSession) -> str:
    """The next `MR-YYYY-NNNN`. The counter moves inside the caller's transaction, so a
    request that fails to save does not use up a number."""
    year = rules.year_of(now)
    counter: dict[str, Any] | None = await db["counters"].find_one_and_update(
        {"_id": rules.counter_key(year)}, {"$inc": {"seq": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER, session=session,
    )
    if counter is None:  # upsert=True always returns the document
        raise RuntimeError("the request counter was not created")
    return rules.format_ref(year, int(counter["seq"]))


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db,
    request_id: str,
    changes: dict[str, Any],
    *,
    now: datetime,
    by: str | None,
    session: AsyncClientSession,
    expected_status: str | None = None,
    expected_version: int | None = None,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply `changes`, bump `version`, and append a `status_history` entry when given.

    `expected_status` makes a status change atomic: it applies only if the request is still
    in the status the caller decided from, so two admins pressing Approve and Deny at once
    cannot both win (409 for the second). `expected_version` is the editor's stale-write check.
    """
    query: dict[str, Any] = {"_id": request_id}
    if expected_status is not None:
        query["status"] = expected_status
    if expected_version is not None:
        query["version"] = expected_version
    update: dict[str, Any] = {
        "$set": {**changes, "updated_at": now, "updated_by": by}, "$inc": {"version": 1},
    }
    if history is not None:
        update["$push"] = {"status_history": history}
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        query, update, return_document=ReturnDocument.AFTER, session=session
    )
    if doc is not None:
        return doc
    current = await col(db).find_one({"_id": request_id}, {"status": 1, "version": 1},
                                     session=session)
    if current is None:
        raise NotFound()
    if expected_status is not None and current["status"] != expected_status:
        raise Conflict("This request was just changed by someone else. Reload and try again",
                       code="request_changed")
    raise VersionConflict()
