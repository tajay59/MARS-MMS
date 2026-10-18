"""The `stations` collection. A client reads only their organization's (rule 3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from mms_common.auth.scope import STATION_OWNER
from mms_common.errors import NotFound
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session, contains, update_versioned


def col(db: Db) -> Any:
    return db["stations"]


@dataclass(frozen=True)
class Filters:
    org_id: str | None = None
    country: str | None = None
    type: str | None = None
    status: str | None = None
    parameter: str | None = None
    q: str | None = None


def _query(viewer: User, f: Filters) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if f.org_id:
        query["owner_org_id"] = f.org_id
    if f.country:
        query["country"] = f.country
    if f.type:
        query["type"] = f.type
    if f.status:
        query["status"] = f.status
    if f.parameter:
        query["parameters"] = f.parameter
    if f.q:
        query["$or"] = [
            {"code": contains(f.q)}, {"name": contains(f.q)}, {"external_id": f.q.strip()},
        ]
    return scoped(viewer, query, STATION_OWNER)


async def search(
    db: Db, viewer: User, f: Filters, *, after: str | None, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """A page in code order, after the code `after`, and the total that match."""
    query = _query(viewer, f)
    total = int(await col(db).count_documents(query))
    if after:
        query = {"$and": [query, {"code": {"$gt": after}}]}
    cursor = col(db).find(query).sort("code", 1).limit(limit)
    return [d async for d in cursor], total


async def facets(db: Db, viewer: User) -> dict[str, list[str]]:
    """The values present, for the list's filter menus (STN-5)."""
    base = scoped(viewer, {}, STATION_OWNER)
    out: dict[str, list[str]] = {}
    for name, path in (("countries", "country"), ("types", "type"),
                       ("parameters", "parameters"), ("org_ids", "owner_org_id")):
        values = await col(db).distinct(path, base)
        out[name] = sorted(v for v in values if v)
    return out


async def get(
    db: Db, station_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any] | None:
    """`viewer=None` is an internal read."""
    query: dict[str, Any] = {"_id": station_id}
    if viewer is not None:
        query = scoped(viewer, query, STATION_OWNER)
    doc: dict[str, Any] | None = await col(db).find_one(query, session=session)
    return doc


async def require(
    db: Db, station_id: str, viewer: User | None = None, session: Session = None
) -> dict[str, Any]:
    doc = await get(db, station_id, viewer, session)
    if doc is None:
        raise NotFound()
    return doc


async def by_codes(db: Db, codes: list[str]) -> dict[str, dict[str, Any]]:
    return {d["code"]: d async for d in col(db).find({"code": {"$in": codes}})}


async def by_external_ids(db: Db, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Stations already imported from the existing system, by its device ID (decision W5-8)."""
    return {d["external_id"]: d async for d in col(db).find({"external_id": {"$in": ids}})}


async def ids_where(db: Db, *, country: str | None, station_id: str | None) -> list[str]:
    query: dict[str, Any] = {}
    if country:
        query["country"] = country
    if station_id:
        query["_id"] = station_id
    return [d["_id"] async for d in col(db).find(query, {"_id": 1})]


async def by_ids(db: Db, ids: list[str]) -> dict[str, dict[str, Any]]:
    return {d["_id"]: d async for d in col(db).find({"_id": {"$in": ids}})}


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def update(
    db: Db,
    station_id: str,
    changes: dict[str, Any],
    *,
    now: datetime,
    by: str,
    expected_version: int | None,
    session: AsyncClientSession,
) -> dict[str, Any]:
    return await update_versioned(
        col(db), station_id, changes, now=now, by=by, expected_version=expected_version,
        session=session,
    )


async def rename_owner(db: Db, org_id: str, name: str, session: Session = None) -> None:
    """Refresh the copied organization name (TRD §3.2 "Consumes"). A copy, so no version."""
    await col(db).update_many(
        {"owner_org_id": org_id, "owner_org_name": {"$ne": name}},
        {"$set": {"owner_org_name": name}},
        session=session,
    )
