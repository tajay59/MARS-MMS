"""audit_events indexes and the chain head (TRD §5.6). The audit user may create indexes
but never update or remove audit_events (TP "Audit insert-only and chain")."""

from __future__ import annotations

from typing import Any

from mms_common import mongo
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.audit import GENESIS


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    events = db["audit_events"]
    await events.create_index("seq", unique=True)
    await events.create_index(
        [("resource.type", ASCENDING), ("resource.id", ASCENDING), ("at", ASCENDING)]
    )
    await events.create_index([("actor.user_id", ASCENDING), ("at", ASCENDING)])
    await events.create_index([("action", ASCENDING), ("at", ASCENDING)])
    await events.create_index([("org_id", ASCENDING), ("at", ASCENDING)])
    await mongo.ensure_processed_events(db)
    await db["audit_state"].update_one(
        {"_id": "chain"}, {"$setOnInsert": {"last_seq": 0, "last_hash": GENESIS}}, upsert=True
    )
