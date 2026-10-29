"""unit_facts (sensor units and when they are due) and `assigned_ids` on request_facts (W19-6).

Rows written before this had no `assigned_ids`; the backfill that runs at every start skips a
row whose version is not newer, so those rows are marked version 0 and the next start writes
them again from operations' snapshot."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["unit_facts"].create_index([("status", 1), ("due_at", 1)])
    await db["unit_facts"].create_index([("station_id", 1)])
    await db["request_facts"].create_index([("assigned_ids", 1), ("status", 1)])
    await db["visit_facts"].create_index([("status", 1), ("planned_start", 1)])
    await db["reports"].create_index([("type", 1), ("status", 1), ("lead_staff_id", 1)])
    await db["request_facts"].update_many(
        {"assigned_ids": {"$exists": False}}, {"$set": {"aggregate_version": 0}}
    )
