"""The collections `/sync` keeps (TRD §5, §7.3; W14-3, W14-5).

`sync_operations`: the answer to each applied operation, by the phone's `op_id`, kept 90 days.
`sync_conflicts`: a day-long marker so a stuck conflict is reported once.
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

DAY = 24 * 60 * 60


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["sync_operations"].create_index("applied_at", expireAfterSeconds=90 * DAY)
    await db["sync_operations"].create_index([("user_id", ASCENDING), ("visit_id", ASCENDING)])
    await db["sync_conflicts"].create_index("at", expireAfterSeconds=DAY)
