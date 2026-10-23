"""The `sync_operations` and `sync_conflicts` collections (TRD §5, §7.3; BSD; W14-3, W14-5).

`sync_operations` holds the answer to each operation a phone got applied, by the phone's `op_id`
(kept 90 days), so asking again returns it at once. Only what was applied is kept: a conflict can
clear (an admin restores a cancelled visit) and the same operation must then be tried again.
`sync_conflicts` is a day-long marker so a phone that keeps retrying a stuck conflict tells the
lead and the admins once, not every five minutes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session


def operations(db: Db) -> Any:
    return db["sync_operations"]


def conflicts(db: Db) -> Any:
    return db["sync_conflicts"]


async def stored(db: Db, op_ids: list[str], session: Session = None) -> dict[str, dict[str, Any]]:
    """The recorded operations among these IDs, by ID (any user's: the caller checks whose)."""
    cursor = operations(db).find({"_id": {"$in": op_ids}}, session=session)
    return {d["_id"]: d async for d in cursor}


async def claim(
    db: Db, *, op_id: str, user_id: str, device_id: str, type_: str, visit_id: str, now: datetime,
    session: AsyncClientSession,
) -> None:
    """Remember an operation, inside the transaction that applies it: either both happen or
    neither does (TRD §7.3). Safe to repeat within one operation."""
    await operations(db).update_one(
        {"_id": op_id},
        {"$setOnInsert": {
            "user_id": user_id, "device_id": device_id, "type": type_, "visit_id": visit_id,
            "result": None, "applied_at": now,
        }},
        upsert=True, session=session,
    )


async def set_result(db: Db, op_id: str, result: dict[str, Any] | None) -> None:
    """What the operation answered, kept so a retry gets the same answer."""
    await operations(db).update_one({"_id": op_id}, {"$set": {"result": result}})


async def first_report(
    db: Db, *, visit_id: str, user_id: str, reason: str, now: datetime, session: AsyncClientSession,
) -> bool:
    """True the first time this person's conflict of this kind on this visit is seen today."""
    key = f"{visit_id}:{user_id}:{reason}"
    existing = await conflicts(db).find_one_and_update(
        {"_id": key}, {"$setOnInsert": {"at": now, "visit_id": visit_id}},
        upsert=True, return_document=ReturnDocument.BEFORE, session=session,
    )
    return existing is None
