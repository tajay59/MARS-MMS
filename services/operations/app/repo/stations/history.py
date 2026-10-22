"""`installations` (SEN-3) and `calibrations` (CAL-1). Both carry `org_id`, copied from the
station when written; stations never change owner (B5), so the copy never goes stale."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User, scoped
from mms_common.errors import NotFound
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session


def installations(db: Db) -> Any:
    return db["installations"]


def calibrations(db: Db) -> Any:
    return db["calibrations"]


# --- Installations ---------------------------------------------------------------------------


async def station_installations(db: Db, station_id: str, viewer: User) -> list[dict[str, Any]]:
    """Newest first: the current units, then what they replaced."""
    query = scoped(viewer, {"station_id": station_id})
    cursor = installations(db).find(query).sort([("installed_at", -1), ("_id", -1)])
    return [d async for d in cursor]


async def unit_installations(db: Db, unit_id: str) -> list[dict[str, Any]]:
    cursor = installations(db).find({"sensor_unit_id": unit_id}).sort("installed_at", -1)
    return [d async for d in cursor]


async def open_installation(
    db: Db, unit_id: str, session: Session = None
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await installations(db).find_one(
        {"sensor_unit_id": unit_id, "removed_at": None}, session=session
    )
    return doc


async def open_at_station(db: Db, station_id: str) -> dict[str, dict[str, Any]]:
    """Unit ID -> its open installation at the station."""
    cursor = installations(db).find({"station_id": station_id, "removed_at": None})
    return {d["sensor_unit_id"]: d async for d in cursor}


async def open_at_station_in(
    db: Db, station_id: str, session: Session = None
) -> list[dict[str, Any]]:
    cursor = installations(db).find({"station_id": station_id, "removed_at": None},
                                    session=session)
    return [d async for d in cursor]


async def installations_by_ids(
    db: Db, ids: list[str], session: Session = None
) -> list[dict[str, Any]]:
    cursor = installations(db).find({"_id": {"$in": ids}}, session=session)
    return [d async for d in cursor]


async def reopen_installation(
    db: Db, installation_id: str, *, now: datetime, by: str | None, session: AsyncClientSession
) -> None:
    """Undo a removal made by a visit's action: the installation is open again, as it was."""
    await installations(db).update_one(
        {"_id": installation_id},
        {"$set": {"removed_at": None, "removal_reason": None, "removed_visit_id": None,
                  "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        session=session,
    )


async def delete_installation(
    db: Db, installation_id: str, session: AsyncClientSession
) -> None:
    """Undo an installation made by a visit's action: exact undo, so the row is removed (its
    `source_action_id` is unique, and the action may be applied again)."""
    await installations(db).delete_one({"_id": installation_id}, session=session)


async def insert_installation(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await installations(db).insert_one(doc, session=session)


async def close_installation(
    db: Db, installation_id: str, *, at: datetime, reason: str | None, now: datetime,
    by: str | None, session: AsyncClientSession, visit_id: str | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] | None = await installations(db).find_one_and_update(
        {"_id": installation_id, "removed_at": None},
        {"$set": {"removed_at": at, "removal_reason": reason, "removed_visit_id": visit_id,
                  "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if doc is None:
        raise NotFound()
    return doc


# --- Calibrations ----------------------------------------------------------------------------


async def search_calibrations(
    db: Db,
    *,
    unit_id: str | None,
    station_id: str | None,
    after: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Staff only (TRD §3.2). Newest first by date."""
    query: dict[str, Any] = {"voided_at": None}  # one undone with its sensor action is not history
    if unit_id:
        query["sensor_unit_id"] = unit_id
    if station_id:
        query["station_id"] = station_id
    if after:
        query["_id"] = {"$lt": after}
    cursor = calibrations(db).find(query).sort([("_id", -1)]).limit(limit)
    return [d async for d in cursor]


async def insert_calibration(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await calibrations(db).insert_one(doc, session=session)


async def void_calibration(
    db: Db, calibration_id: str, *, now: datetime, by: str | None, session: AsyncClientSession
) -> dict[str, Any]:
    """A calibration undone with its sensor action stays on record, marked, and leaves the
    history lists."""
    doc: dict[str, Any] | None = await calibrations(db).find_one_and_update(
        {"_id": calibration_id},
        {"$set": {"voided_at": now, "updated_at": now, "updated_by": by}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if doc is None:
        raise NotFound()
    return doc
