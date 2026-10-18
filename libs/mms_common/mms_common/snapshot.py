"""Read-model backfill support (TRD §8.6).

Read models are rebuilt from CURRENT state through `/internal/snapshot/{entity}`, never by
replaying the outbox (Kafka keeps 14 days, the outbox 7). Both sides share the
`aggregate_version` guard, so events that arrive during a backfill are applied or skipped
correctly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError

MAX_LIMIT = 500


class SnapshotPage(BaseModel):
    items: list[dict[str, Any]]
    next_after: str | None  # pass as `after` for the next page; None when done


async def page(
    collection: AsyncCollection[dict[str, Any]],
    *,
    after: str | None = None,
    limit: int = MAX_LIMIT,
    base_filter: dict[str, Any] | None = None,
) -> SnapshotPage:
    """One page of current documents in `_id` order (UUIDv7 = creation order)."""
    limit = max(1, min(limit, MAX_LIMIT))
    query: dict[str, Any] = dict(base_filter or {})
    if after is not None:
        query["_id"] = {"$gt": after}
    items = [doc async for doc in collection.find(query).sort("_id", 1).limit(limit + 1)]
    more = len(items) > limit
    items = items[:limit]
    return SnapshotPage(items=items, next_after=str(items[-1]["_id"]) if more else None)


async def upsert_if_newer(
    collection: AsyncCollection[dict[str, Any]],
    doc: dict[str, Any],
    *,
    session: AsyncClientSession | None = None,
) -> bool:
    """Write `doc` only if its `aggregate_version` is newer than the stored one.

    Returns True when written. Equal or older versions are ignored, so applying an event
    and a snapshot in either order ends in the same state.

    It reads first and never provokes a duplicate-key error: inside a transaction (a
    consumer's, TRD §8.5) that error aborts the transaction on the server even when caught,
    and the driver then retries the whole transaction until its timeout. A concurrent writer
    shows up as a write conflict instead, which the transaction retries cleanly.
    """
    for _ in range(2):
        current = await collection.find_one(
            {"_id": doc["_id"]}, {"aggregate_version": 1}, session=session
        )
        if current is not None:
            if current.get("aggregate_version", 0) >= doc["aggregate_version"]:
                return False
            result = await collection.replace_one(
                {"_id": doc["_id"], "aggregate_version": {"$lt": doc["aggregate_version"]}},
                doc,
                session=session,
            )
            return result.matched_count == 1
        if session is not None and session.in_transaction:
            await collection.insert_one(doc, session=session)
            return True
        try:
            await collection.insert_one(doc, session=session)
        except DuplicateKeyError:
            continue  # inserted meanwhile (no transaction): compare with that one
        return True
    return False
