"""`email_queue` indexes in the notification database (account emails, NOT-3)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.repo import emails


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await emails.ensure_indexes(db)
