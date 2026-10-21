"""`digest_runs`: one document per ISO week that the calibration digest has gone out for (CAL-5).
The document is claimed first, so a restart or a second instance can't send it twice, and it
keeps the list the emails are rendered from."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]


def col(db: Db) -> Any:
    return db["digest_runs"]


async def claim(
    db: Db, week: str, now: datetime, items: list[dict[str, Any]], within_days: int,
    session: AsyncClientSession,
) -> bool:
    """True for the one caller that claims `week`. An upsert, not an insert: a duplicate-key
    error would abort the transaction on the server and be retried until its timeout."""
    result = await col(db).update_one(
        {"_id": week},
        {"$setOnInsert": {"at": now, "items": items, "within_days": within_days}},
        upsert=True, session=session,
    )
    return result.upserted_id is not None


async def get(db: Db, week: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = await col(db).find_one({"_id": week})
    return found
