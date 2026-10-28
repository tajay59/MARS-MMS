"""Aggregates for the dashboards (W19-7) over the read model and the reports.

Every function takes the organization to scope by. The route passes the caller's own for a
client and nothing for staff, so a parameter in the request can never widen a client's view
(rule 3).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.domain import dashboard as dash
from app.domain import readmodel as rm

Db = AsyncDatabase[dict[str, Any]]
Rows = list[dict[str, Any]]


def _scope(org_id: str | None, **more: Any) -> dict[str, Any]:
    return {**more, **({"org_id": org_id} if org_id else {})}


async def _group(db: Db, collection: str, match: dict[str, Any], key: Any) -> Rows:
    pipeline: list[dict[str, Any]] = [
        {"$match": match}, {"$group": {"_id": key, "n": {"$sum": 1}}},
    ]
    return [r async for r in await db[collection].aggregate(pipeline)]


async def requests_by_status(db: Db, org_id: str | None) -> list[dict[str, Any]]:
    match = _scope(org_id, status={"$in": list(dash.OPEN_STATUSES)})
    return dash.by_status(await _group(db, rm.REQUESTS, match, "$status"))


async def count_requests(db: Db, org_id: str | None, status: str) -> int:
    return int(await db[rm.REQUESTS].count_documents(_scope(org_id, status=status)))


async def my_assigned(db: Db, user_id: str) -> int:
    """Requests someone put this person on and that are still being worked."""
    return int(await db[rm.REQUESTS].count_documents(
        {"assigned_ids": user_id, "status": {"$in": list(dash.WORKING_STATUSES)}}
    ))


async def station_status(db: Db, org_id: str | None) -> dict[str, int]:
    return dash.station_counts(await _group(db, rm.STATIONS, _scope(org_id), "$status"))


async def stations_by_country(db: Db) -> list[dict[str, Any]]:
    rows = await _group(db, rm.STATIONS, {}, {"country": "$country", "status": "$status"})
    return dash.by_country(rows)


async def upcoming_visits(
    db: Db, now: datetime, *, org_id: str | None = None, staff_id: str | None = None
) -> int:
    """Planned visits that have not started. Mine: ones I am on."""
    match = _scope(org_id, status="planned", planned_start={"$gte": now})
    if staff_id:
        match["staff_ids"] = staff_id
    return int(await db[rm.VISITS].count_documents(match))


async def calibrations_due(db: Db, now: datetime) -> tuple[int, int]:
    """(overdue, due within the next 30 days) among installed units (CAL-4)."""
    installed = {"status": "installed", "due_at": {"$ne": None}}
    overdue = await db[rm.UNITS].count_documents({**installed, "due_at": {"$lt": now}})
    soon = await db[rm.UNITS].count_documents(
        {**installed, "due_at": {"$gte": now, "$lt": now + timedelta(days=dash.DUE_WITHIN_DAYS)}}
    )
    return int(overdue), int(soon)


async def failed_calibrations(db: Db) -> int:
    """Units whose newest calibration that still counts failed and that are still in service
    (CAL-6). A later passing calibration clears it; a retired unit is no one's follow-up."""
    pipeline: list[dict[str, Any]] = [
        {"$match": {"voided": {"$ne": True}}},
        {"$sort": {"at": -1}},
        {"$group": {"_id": "$sensor_unit_id", "result": {"$first": "$result"}}},
        {"$match": {"result": "fail"}},
    ]
    failed = [r["_id"] async for r in await db[rm.CALIBRATIONS].aggregate(pipeline)]
    if not failed:
        return 0
    return int(await db[rm.UNITS].count_documents(
        {"_id": {"$in": failed}, "status": {"$ne": "retired"}}
    ))


async def drafts_awaiting(
    db: Db, *, lead_id: str | None = None, limit: int = dash.LIST_LIMIT
) -> tuple[int, Rows]:
    """Visit reports not yet final: how many, and the oldest few (the lead's own for a
    technician)."""
    match: dict[str, Any] = {"type": "visit", "status": {"$in": ["draft", "finalizing"]}}
    if lead_id:
        match["lead_staff_id"] = lead_id
    total = int(await db["reports"].count_documents(match))
    oldest = [r async for r in db["reports"].find(match).sort("ended_at", 1).limit(limit)]
    return total, oldest


async def reports_for_client(db: Db, org_id: str, limit: int = 20) -> Rows:
    """The newest reports a client may read, before the route filters them (the presenter owns
    that rule)."""
    found = db["reports"].find(
        {"org_id": org_id, "status": {"$in": ["final", "superseded"]}}
    ).sort("finalized_at", -1).limit(limit)
    return [r async for r in found]
