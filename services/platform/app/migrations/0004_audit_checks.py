"""audit_checks: the integrity checks of the audit chain and their results (AUD-5, W19-4).
They live in the notification database: the audit user may not update anything in
`audit_events`, and a result is not part of the chain."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    checks = db["audit_checks"]
    await checks.create_index([("status", ASCENDING), ("requested_at", ASCENDING)])
    await checks.create_index([("finished_at", DESCENDING)], sparse=True)
