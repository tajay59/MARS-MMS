"""Indexes for requests (TRD §5.2)."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    requests = db["requests"]
    # MR-YYYY-NNNN is unique; the counter hands out each number once
    await requests.create_index("ref", unique=True)
    # The list: a client's own organization, newest first, by status
    await requests.create_index([("org_id", ASCENDING), ("status", ASCENDING),
                                 ("_id", DESCENDING)])
    await requests.create_index([("status", ASCENDING), ("_id", DESCENDING)])
    await requests.create_index("station_ids")
    await requests.create_index("assigned_staff_ids")
