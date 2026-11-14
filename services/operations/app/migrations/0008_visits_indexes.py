"""Indexes for visits (TRD §5.4): a request's visits by date, a person's visits, a status."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    visits = db["site_visits"]
    # VR-YYYY-NNNN-NN is unique; the counter hands out each number once
    await visits.create_index("ref", unique=True)
    await visits.create_index([("request_id", ASCENDING), ("planned_start", ASCENDING)])
    # "My visits": attending staff, soonest first
    await visits.create_index([("staff_ids", ASCENDING), ("planned_start", ASCENDING)])
    await visits.create_index([("status", ASCENDING), ("planned_start", ASCENDING)])
    await visits.create_index([("org_id", ASCENDING), ("planned_start", ASCENDING)])
