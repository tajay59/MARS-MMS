"""Indexes for the sensor models, configuration versions and installations that the Station
asset, Sensor reliability and Configuration history summaries read (W19-6). The collections are
filled by events and by the start-up backfill from operations' snapshots."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["installation_facts"].create_index([("station_id", 1), ("removed_at", 1)])
    await db["installation_facts"].create_index([("model_id", 1), ("installed_at", 1)])
    await db["config_facts"].create_index([("station_id", 1), ("created_at", -1)])
