"""Indexes of the read model (TRD §5.4). The summary reports and the dashboard filter by
organization first, then status or date."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["request_facts"].create_index([("org_id", 1), ("status", 1)])
    await db["request_facts"].create_index([("submitted_at", 1)])
    await db["visit_facts"].create_index([("org_id", 1), ("ended_at", 1)])
    await db["visit_facts"].create_index([("request_id", 1)])
    await db["station_facts"].create_index([("org_id", 1), ("country", 1)])
    await db["calibration_facts"].create_index([("org_id", 1), ("due_at", 1)])
    await db["calibration_facts"].create_index([("station_id", 1), ("at", -1)])
