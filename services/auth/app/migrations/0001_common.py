"""Indexes every service needs: the outbox (TRD §8.2) and `processed_events` (§8.5)."""

from __future__ import annotations

from typing import Any

from mms_common import mongo, outbox
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await outbox.ensure_indexes(db["outbox"])
    await mongo.ensure_processed_events(db)
