"""The read-model collections (TRD §5.4): written only when the row is newer than the stored one."""

from __future__ import annotations

from typing import Any

from mms_common.snapshot import upsert_if_newer
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import readmodel as rm

Db = AsyncDatabase[dict[str, Any]]


async def put(
    db: Db, collection: str, row: dict[str, Any], session: AsyncClientSession | None = None
) -> bool:
    """Write `row` if its `aggregate_version` is newer. A visit keeps the times and counts that
    later events do not repeat (`started_at` survives `visit.station_arrived`)."""
    if collection == rm.INSTALLS:
        # Merged field by field, in any order (an installation is written by two events)
        fields = {k: v for k, v in row.items() if k != "_id"}
        await db[collection].update_one({"_id": row["_id"]}, {"$set": fields}, upsert=True,
                                        session=session)
        return True
    if collection == rm.VISITS:
        stored = await db[collection].find_one({"_id": row["_id"]}, session=session)
        if stored is not None:
            row = rm.keep_from(stored, row, rm.VISIT_KEEP)
    return await upsert_if_newer(db[collection], row, session=session)


async def void_calibration(
    db: Db, calibration_id: str, session: AsyncClientSession | None = None
) -> None:
    """A voided calibration no longer counts. It reuses the version of the record it voids, so it
    is applied by itself and never lost to the version guard."""
    await db[rm.CALIBRATIONS].update_one(
        {"_id": calibration_id}, {"$set": {"voided": True}}, session=session
    )
