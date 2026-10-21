"""Indexes for notifications and the user directory (TRD §5.5)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.repo import notifications


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await notifications.ensure_indexes(db)
