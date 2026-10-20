"""Report jobs are listed by who asked, newest first."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["report_jobs"].create_index([("requested_by", 1), ("created_at", -1)])
