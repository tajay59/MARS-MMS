"""Indexes for searching, exporting and the History tab (W19), paged by `seq`, newest first.
The audit user may create indexes but never change or remove a record (rule 10)."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    events = db["audit_events"]
    await events.create_index([("resource.type", ASCENDING), ("resource.id", ASCENDING),
                               ("seq", ASCENDING)])
    await events.create_index([("actor.user_id", ASCENDING), ("seq", ASCENDING)])
    await events.create_index([("action", ASCENDING), ("seq", ASCENDING)])
    await events.create_index([("org_id", ASCENDING), ("seq", ASCENDING)])
    await events.create_index([("at", ASCENDING)])
    # A page's History also lists the events that name it in their data
    for key in ("request_id", "visit_id", "station_id"):
        await events.create_index([(f"metadata.{key}", ASCENDING), ("seq", ASCENDING)],
                                  sparse=True)
