"""`audit_checks` in the notification database (W19-4): a check is queued by an admin or by
the nightly run, taken by one worker, and ends `passed`, `broken` or `failed`."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]
# A check a worker took and never finished (it died) is taken again after this long.
STALE = timedelta(minutes=15)


async def create(
    db: Db, *, check_id: str, kind: str, now: datetime, by: dict[str, Any] | None
) -> bool:
    """Queue a check. False when one with this id exists (the nightly id is the date)."""
    if await db["audit_checks"].find_one({"_id": check_id}, {"_id": 1}) is not None:
        return False
    await db["audit_checks"].insert_one({
        "_id": check_id, "kind": kind, "status": "queued", "requested_at": now,
        "requested_by": by, "checked": 0, "total": None, "first_break_seq": None,
        "started_at": None, "finished_at": None, "attempts": 0, "error": None,
    })
    return True


async def claim_next(db: Db, now: datetime) -> dict[str, Any] | None:
    """Take the oldest queued check, or one a dead worker left running."""
    return await db["audit_checks"].find_one_and_update(
        {"$or": [{"status": "queued"},
                 {"status": "running", "started_at": {"$lt": now - STALE}}]},
        {"$set": {"status": "running", "started_at": now}, "$inc": {"attempts": 1}},
        sort=[("requested_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def progress(db: Db, check_id: str, *, checked: int, total: int) -> None:
    await db["audit_checks"].update_one(
        {"_id": check_id, "status": "running"}, {"$set": {"checked": checked, "total": total}}
    )


async def finish(
    db: Db, check_id: str, *, status: str, now: datetime, checked: int, total: int,
    first_break_seq: int | None = None, error: str | None = None,
) -> None:
    await db["audit_checks"].update_one(
        {"_id": check_id},
        {"$set": {"status": status, "finished_at": now, "checked": checked, "total": total,
                  "first_break_seq": first_break_seq, "error": error}},
    )


async def get(db: Db, check_id: str) -> dict[str, Any] | None:
    return await db["audit_checks"].find_one({"_id": check_id})


async def latest_finished(db: Db) -> dict[str, Any] | None:
    return await db["audit_checks"].find_one(
        {"status": {"$in": ["passed", "broken"]}}, sort=[("finished_at", -1)]
    )
