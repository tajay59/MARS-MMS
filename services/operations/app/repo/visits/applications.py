"""The `sensor_applications` collection (TRD §3.2.3; BSD): what each sensor action of a visit did
to the inventory, so it can be undone exactly. `_id` is the action's id (made on the device,
rule 9), which is why applying it twice is impossible."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.repo.stations.common import Db, Session


def col(db: Db) -> Any:
    return db["sensor_applications"]


async def for_station(
    db: Db, visit_id: str, station_id: str, session: Session = None
) -> list[dict[str, Any]]:
    """In the order they were applied."""
    cursor = col(db).find({"visit_id": visit_id, "station_id": station_id}, session=session)
    return sorted([d async for d in cursor], key=lambda d: d["seq"])


async def next_seq(db: Db, visit_id: str, station_id: str, session: AsyncClientSession) -> int:
    """One more than the highest applied so far; moved inside the transaction that uses it."""
    doc: dict[str, Any] | None = await db["counters"].find_one_and_update(
        {"_id": f"applications:{visit_id}:{station_id}"}, {"$inc": {"seq": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER, session=session,
    )
    return int(doc["seq"]) if doc else 1


async def insert(db: Db, doc: dict[str, Any], session: AsyncClientSession) -> None:
    await col(db).insert_one(doc, session=session)


async def delete(db: Db, action_id: str, session: AsyncClientSession) -> None:
    await col(db).delete_one({"_id": action_id}, session=session)


def row(
    action_id: str, visit_id: str, station_id: str, seq: int, action_hash: str,
    effects: dict[str, Any], now: datetime,
) -> dict[str, Any]:
    return {"_id": action_id, "visit_id": visit_id, "station_id": station_id, "seq": seq,
            "action_hash": action_hash, "effects": effects, "applied_at": now}
