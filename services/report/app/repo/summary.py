"""The rows a summary report is made of (W19-8): read-model queries, scoped before anything else.

A client's report is scoped twice: by their organization and by the stations that organization
owns. A station that is not theirs is 404, as everywhere (rule 4). No query here goes to another
service: a summary reads only the read model (TRD 11.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from mms_common.errors import NotFound, ValidationFailed
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import dashboard as dash
from app.domain import readmodel as rm
from app.domain.summary import MAX_ROWS, Kind, Period

Db = AsyncDatabase[dict[str, Any]]
Rows = list[dict[str, Any]]


class TooLarge(Exception):  # noqa: N818 - reads as the instruction it is
    """More rows than a summary should hold: the job fails and asks for a narrower one."""


@dataclass(frozen=True)
class Scope:
    org_id: str | None
    station_ids: list[str] | None  # None: no station filter at all


async def resolve(
    db: Db, *, org_id: str | None, country: str | None, station_ids: list[str] | None
) -> tuple[Scope, dict[str, dict[str, Any]]]:
    """The stations a report covers. Asking for a station outside the organization (or one that
    does not exist) is 404."""
    match: dict[str, Any] = {}
    if org_id:
        match["org_id"] = org_id
    if country:
        match["country"] = country
    if station_ids:
        match["_id"] = {"$in": station_ids}
    found = {s["_id"]: s async for s in db[rm.STATIONS].find(match)}
    if station_ids and set(station_ids) - found.keys():
        raise NotFound()
    restricted = bool(org_id or country or station_ids)
    return Scope(org_id, list(found) if restricted else None), found


def _where(
    scope: Scope, station_field: str = "station_ids", *, org: bool = True
) -> dict[str, Any]:
    """The scope as a filter. Units have no organization of their own: their station's is
    enough, because `resolve` already narrowed the stations to the organization's."""
    flt: dict[str, Any] = {}
    if scope.org_id and org:
        flt["org_id"] = scope.org_id
    if scope.station_ids is not None:
        flt[station_field] = {"$in": scope.station_ids}
    return flt


def _within(field: str, p: Period) -> dict[str, Any]:
    return {field: {"$gte": p.start, "$lt": p.end}}


async def _rows(db: Db, collection: str, flt: dict[str, Any]) -> Rows:
    rows = [r async for r in db[collection].find(flt).limit(MAX_ROWS + 1)]
    if len(rows) > MAX_ROWS:
        raise TooLarge
    return rows


async def _per_station(db: Db, collection: str, flt: dict[str, Any], *, field: str,
                       value: Any = 1, op: str = "$sum") -> dict[str, Any]:
    pipeline: list[dict[str, Any]] = [{"$match": flt}]
    if field == "station_ids":
        pipeline.append({"$unwind": "$station_ids"})
    pipeline.append({"$group": {"_id": f"${field}" if field != "station_ids" else "$station_ids",
                                "v": {op: value}}})
    return {r["_id"]: r["v"] async for r in await db[collection].aggregate(pipeline)}


async def fetch(
    db: Db, kind: Kind, scope: Scope, stations: dict[str, dict[str, Any]], p: Period | None,
    *, now: datetime, due_in_days: int, zone: str,
) -> dict[str, Any]:
    """The rows `domain.summary.build` needs for `kind`."""
    data: dict[str, Any] = {"stations": stations, "now": now, "zone": zone,
                            "due_in_days": due_in_days}
    visits_in = {"status": "ended", **_where(scope)}
    if p is not None:
        visits_in.update(_within("ended_at", p))
    if kind is Kind.STATION_HISTORY and p is not None:
        data["visits"] = await _rows(db, rm.VISITS, visits_in)
        data["requests"] = await _rows(
            db, rm.REQUESTS, {**_where(scope), **_within("submitted_at", p)})
        calibrations = await _rows(db, rm.CALIBRATIONS, {
            "voided": {"$ne": True}, **_within("at", p), **_where(scope, "station_id", org=False)})
        data["calibrations"] = calibrations
        request_ids = list({v["request_id"] for v in data["visits"]})
        found = await _rows(db, rm.REQUESTS, {"_id": {"$in": request_ids}})
        data["request_refs"] = {r["_id"]: r["ref"] for r in found}
        unit_ids = [c["sensor_unit_id"] for c in calibrations]
        units = await _rows(db, rm.UNITS, {"_id": {"$in": unit_ids}})
        data["serials"] = {u["_id"]: u["serial"] for u in units}
    elif kind is Kind.CLIENT_ACTIVITY and p is not None:
        data["requests"] = await _rows(
            db, rm.REQUESTS, {**_where(scope), **_within("submitted_at", p)})
        data["visits"] = await _rows(db, rm.VISITS, {
            "status": "ended", "request_id": {"$in": [r["_id"] for r in data["requests"]]}})
    elif kind is Kind.REQUEST_TURNAROUND and p is not None:
        data["requests"] = await _rows(db, rm.REQUESTS, {
            "status": "closed", **_where(scope), **_within("closed_at", p)})
    elif kind is Kind.CALIBRATION_DUE:
        data["units"] = await _rows(db, rm.UNITS, {
            "status": "installed", "due_at": {"$lt": now + timedelta(days=due_in_days)},
            **_where(scope, "station_id", org=False)})
    elif kind is Kind.NETWORK_STATUS:
        restrict = _where(scope)
        data["last_visit"] = await _per_station(
            db, rm.VISITS, {"status": "ended", **restrict}, field="station_ids",
            value="$ended_at", op="$max")
        data["open_requests"] = await _per_station(
            db, rm.REQUESTS, {"status": {"$in": list(dash.OPEN_STATUSES)}, **restrict},
            field="station_ids")
        data["overdue_units"] = await _per_station(
            db, rm.UNITS, {"status": "installed", "due_at": {"$lt": now},
                           **_where(scope, "station_id", org=False)}, field="station_id")
    elif kind is Kind.MONTHLY_SUMMARY and p is not None:
        data["submitted"] = await _rows(
            db, rm.REQUESTS, {**_where(scope), **_within("submitted_at", p)})
        data["closed"] = await _rows(db, rm.REQUESTS, {
            "status": "closed", **_where(scope), **_within("closed_at", p)})
        data["visits"] = await _rows(db, rm.VISITS, visits_in)
    elif kind is Kind.ANNUAL_SUMMARY and p is not None:
        data["submitted"] = await _rows(
            db, rm.REQUESTS, {**_where(scope), **_within("submitted_at", p)})
        data["closed"] = await _rows(db, rm.REQUESTS, {
            "status": "closed", **_where(scope), **_within("closed_at", p)})
        data["visits"] = await _rows(db, rm.VISITS, visits_in)
        data["calibrations"] = await _rows(db, rm.CALIBRATIONS, {
            "voided": {"$ne": True}, **_within("at", p), **_where(scope, "station_id", org=False)})
    else:
        raise ValidationFailed("This report needs a period", code="invalid_period")
    return data
