"""Index for the Client Review clock (TRD §3.2, §5.2): the daily job reads the requests that are
waiting for the client, oldest review first."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["requests"].create_index([("status", ASCENDING), ("review_started_at", ASCENDING)])
