"""The `site_visits` collection (TRD §5.4). A client reads only their organization's visits
(rule 3, scoped on `org_id`); staff read all."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from mms_common.errors import Conflict, NotFound, VersionConflict
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.visits.state import LIVE
from app.repo.stations.common import Db, Session


def col(db: Db) -> Any:
    return db["site_visits"]


def counter_key(request_ref: str) -> str:
    """`VR-2026-0042` for the request `MR-2026-0042`: its visits are numbered from one."""
    return "VR-" + request_ref.split("-", 1)[1]


def format_ref(request_ref: str, seq: int) -> str:
    """`VR-2026-0042-01`: the request's number and the visit's own (TRD §5.4)."""
    return f"{counter_key(request_ref)}-{seq:02d}"


async def next_ref(db: Db, request_ref: str, session: AsyncClientSession) -> str:
    """The counter moves inside the caller's transaction, so a visit that fails to save does
    not use up a number."""
    counter: dict[str, Any] | None = await db["counters"].find_one_and_update(
        {"_id": counter_key(request_ref)}, {"$inc": {"seq": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER, session=session,
    )
    if counter is None:  # upsert=True always returns the document
        raise RuntimeError("the visit counter was not created")
    return format_ref(request_ref, int(counter["seq"]))


async def get(
    db: Db, visit_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """`viewer=None` is an internal read."""
    query: dict[str, Any] = {"_id": visit_id}
    if viewer is not None:
        query = scoped(viewer, query)
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, visit_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any]:
    doc = await get(db, visit_id, viewer, session)
    if doc is None:
        raise NotFound()
    return doc


async def for_request(
    db: Db, request_id: str, viewer: User | None = None, session: Session = None
) -> list[dict[str, Any]]:
    """A request's visits, soonest first."""
    query: dict[str, Any] = {"request_id": request_id}
    if viewer is not None:
        query = scoped(viewer, query)
    cursor = col(db).find(query, session=session).sort([("planned_start", 1), ("_id", 1)])
    return [d async for d in cursor]


async def live_for_request(
    db: Db, request_id: str, session: Session = None, *, excluding: str | None = None
) -> list[dict[str, Any]]:
    """The request's planned and started visits (W10-5), other than `excluding`."""
    query: dict[str, Any] = {"request_id": request_id, "status": {"$in": [s.value for s in LIVE]}}
    if excluding:
        query["_id"] = {"$ne": excluding}
    return [d async for d in col(db).find(query, session=session)]


async def has_live(db: Db, request_id: str, session: Session = None) -> bool:
    found = await col(db).find_one(
        {"request_id": request_id, "status": {"$in": [s.value for s in LIVE]}}, {"_id": 1},
        session=session,
    )
    return found is not None


async def search(
    db: Db, viewer: User, *, request_id: str | None = None, staff_id: str | None = None,
    statuses: tuple[str, ...] = (), start_from: datetime | None = None,
    start_to: datetime | None = None, after: str | None = None, limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Soonest first, and how many match."""
    query: dict[str, Any] = {}
    if request_id:
        query["request_id"] = request_id
    if staff_id:
        query["staff_ids"] = staff_id
    if statuses:
        query["status"] = {"$in": list(statuses)}
    window: dict[str, datetime] = {}
    if start_from:
        window["$gte"] = start_from
    if start_to:
        window["$lt"] = start_to
    if window:
        query["planned_start"] = window
    query = scoped(viewer, query)
    total = int(await col(db).count_documents(query))
    if after:
        query = {"$and": [query, {"_id": {"$gt": after}}]}
    cursor = col(db).find(query).sort([("planned_start", 1), ("_id", 1)]).limit(limit)
    return [d async for d in cursor], total


async def mine(db: Db, user: User, *, limit: int = 100) -> list[dict[str, Any]]:
    """The visits I attend that are planned or under way, soonest first (AFD "My upcoming
    visits")."""
    cursor = col(db).find(
        {"staff_ids": user.id, "status": {"$in": [s.value for s in LIVE]}}
    ).sort([("planned_start", 1), ("_id", 1)]).limit(limit)
    return [d async for d in cursor]


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db, visit_id: str, changes: dict[str, Any], *, now: datetime, by: str | None,
    session: AsyncClientSession, expected_status: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Apply `changes` and bump `version`. `expected_status` makes a move atomic: it applies only
    if the visit is still in the status the caller decided from, so two people pressing Start
    and Cancel at once cannot both win. `expected_version` is the editor's stale-write check."""
    query: dict[str, Any] = {"_id": visit_id}
    if expected_status is not None:
        query["status"] = expected_status
    if expected_version is not None:
        query["version"] = expected_version
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        query,
        {"$set": {**changes, "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if doc is not None:
        return doc
    current = await col(db).find_one({"_id": visit_id}, {"status": 1, "version": 1},
                                     session=session)
    if current is None:
        raise NotFound()
    if expected_status is not None and current["status"] != expected_status:
        raise Conflict("This visit was just changed by someone else. Reload and try again",
                       code="visit_changed")
    raise VersionConflict()


async def set_station(
    db: Db, visit_id: str, station_id: str, fields: dict[str, Any], *, now: datetime, by: str,
    session: AsyncClientSession,
) -> dict[str, Any]:
    """Set fields on one station of a started visit (arrival, departure) without replacing the
    others: two owners arriving at two stations at once do not collide."""
    sets = {f"stations.$[s].{k}": v for k, v in fields.items()}
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": visit_id, "status": "started"},
        {"$set": {**sets, "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        array_filters=[{"s.station_id": station_id}],
        return_document=ReturnDocument.AFTER, session=session,
    )
    if doc is None:
        raise Conflict("This visit was just changed by someone else. Reload and try again",
                       code="visit_changed")
    return doc


async def next_visibility_seq(db: Db, visit_id: str, session: AsyncClientSession) -> int:
    """The number for a request to show or hide a visit's files (W11-28). Media applies only the
    newest per file, so every request from a visit, at its end or for one element later, takes the
    next number in the request's transaction. It starts above the visit's own version, which
    numbered these requests before the board."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": visit_id},
        [{"$set": {"visibility_seq": {"$add": [{"$max": ["$visibility_seq", "$version"]}, 1]}}}],
        return_document=ReturnDocument.AFTER, session=session,
    )
    if doc is None:
        raise NotFound()
    return int(doc["visibility_seq"])


async def set_prepared_on(
    db: Db, visit_id: str, entries: list[dict[str, Any]], session: AsyncClientSession
) -> dict[str, Any]:
    """Where the visit is prepared (W13-9). Not a change to the visit: `version` stays, so a
    person editing the visit is not told their copy is stale because a phone was prepared."""
    doc: dict[str, Any] | None = await col(db).find_one_and_update(
        {"_id": visit_id}, {"$set": {"prepared_on": entries}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if doc is None:
        raise NotFound()
    return doc

