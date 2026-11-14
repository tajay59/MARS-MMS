"""The `sensor_units` collection (SEN-2). Scoped by `current_org_id` (rule 3): a client sees
a unit only while it is installed at one of their stations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from mms_common.auth.scope import UNIT_HOLDER
from mms_common.errors import NotFound
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session, contains, update_versioned


def col(db: Db) -> Any:
    return db["sensor_units"]


@dataclass(frozen=True)
class Filters:
    status: str | None = None
    model_id: str | None = None
    station_id: str | None = None
    q: str | None = None  # serial


async def search(
    db: Db, viewer: User, f: Filters, *, after: str | None, limit: int
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if f.status:
        query["status"] = f.status
    if f.model_id:
        query["model_id"] = f.model_id
    if f.station_id:
        query["current_station_id"] = f.station_id
    if f.q:
        query["serial"] = contains(f.q)
    if after:
        query["_id"] = {"$gt": after}
    cursor = col(db).find(scoped(viewer, query, UNIT_HOLDER)).sort("_id", 1).limit(limit)
    return [d async for d in cursor]


async def counts_by_model(db: Db) -> dict[str, dict[str, int]]:
    """Units of each model by status, for the catalogue (staff only: no scoping)."""
    found: dict[str, dict[str, int]] = {}
    pipeline = [{"$group": {"_id": {"m": "$model_id", "s": "$status"}, "n": {"$sum": 1}}}]
    async for row in await col(db).aggregate(pipeline):
        found.setdefault(row["_id"]["m"], {})[row["_id"]["s"]] = row["n"]
    return found


async def get(
    db: Db, unit_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    query: dict[str, Any] = {"_id": unit_id}
    if viewer is not None:
        query = scoped(viewer, query, UNIT_HOLDER)
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, unit_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any]:
    doc = await get(db, unit_id, viewer, session)
    if doc is None:
        raise NotFound()
    return doc


async def installed_at(
    db: Db, station_id: str, viewer: User | None = None, session: Session = None
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"current_station_id": station_id, "status": "installed"}
    if viewer is not None:
        query = scoped(viewer, query, UNIT_HOLDER)
    cursor = col(db).find(query, session=session).sort("current_parameter", 1)
    return [d async for d in cursor]


async def next_due_by_station(db: Db, station_ids: list[str]) -> dict[str, datetime]:
    """The earliest calibration due date among each station's installed units."""
    pipeline: list[dict[str, Any]] = [
        {"$match": {"current_station_id": {"$in": station_ids}, "status": "installed",
                    "calibration_due_at": {"$ne": None}}},
        {"$group": {"_id": "$current_station_id", "due": {"$min": "$calibration_due_at"}}},
    ]
    return {row["_id"]: row["due"] async for row in await col(db).aggregate(pipeline)}


async def find_by_serial(
    db: Db, model_id: str, serial: str, session: Session = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await col(db).find_one(
        {"model_id": model_id, "serial": serial}, session=session
    )
    return doc


async def by_model_serial(db: Db) -> dict[tuple[str, str], dict[str, Any]]:
    cursor = col(db).find({}, {"model_id": 1, "serial": 1, "status": 1})
    return {(d["model_id"], d["serial"]): d async for d in cursor}


async def using_default_interval(
    db: Db, model_id: str, session: AsyncClientSession
) -> list[dict[str, Any]]:
    """Units of a model that follow its default interval (no override)."""
    cursor = col(db).find(
        {"model_id": model_id, "calibration_interval_days": None}, session=session
    )
    return [d async for d in cursor]


async def due(
    db: Db,
    *,
    until: datetime,
    org_id: str | None,
    station_ids: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Units overdue or due by `until` (CAL-4), soonest first. Retired units are left out.
    The list is bounded by `limit` rather than paged: it is a work list, not an archive."""
    query: dict[str, Any] = {
        "calibration_due_at": {"$ne": None, "$lte": until},
        "status": {"$ne": "retired"},
    }
    if org_id:
        query["current_org_id"] = org_id
    if station_ids is not None:
        query["current_station_id"] = {"$in": station_ids}
    cursor = col(db).find(query).sort([("calibration_due_at", 1), ("_id", 1)]).limit(limit)
    return [d async for d in cursor]


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db, unit_id: str, changes: dict[str, Any], *, now: datetime, by: str | None,
    expected_version: int | None, session: AsyncClientSession,
) -> dict[str, Any]:
    return await update_versioned(
        col(db), unit_id, changes, now=now, by=by, expected_version=expected_version,
        session=session,
    )


async def by_ids(db: Db, ids: list[str], session: Session = None) -> list[dict[str, Any]]:
    cursor = col(db).find({"_id": {"$in": ids}}, session=session)
    return [d async for d in cursor]


async def by_serials(db: Db, serials: list[str], session: Session = None) -> list[dict[str, Any]]:
    """Every unit with one of these serials, whatever its model (a serial is unique only within
    its model)."""
    cursor = col(db).find({"serial": {"$in": serials}}, session=session)
    return [d async for d in cursor]


async def delete(db: Db, unit_id: str, session: AsyncClientSession) -> None:
    await col(db).delete_one({"_id": unit_id}, session=session)
