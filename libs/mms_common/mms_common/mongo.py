"""MongoDB helpers. One database and one DB user per service (CLAUDE.md rule 1).

Run the record update and its outbox insert inside `in_transaction` (rule 2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

PROCESSED_EVENTS_TTL_DAYS = 30  # TRD §5


def connect(uri: str) -> AsyncMongoClient[dict[str, Any]]:
    # Writes need a majority so a transaction survives a primary failover.
    return AsyncMongoClient(uri, tz_aware=True, retryWrites=True, w="majority")


async def in_transaction[T](
    client: AsyncMongoClient[dict[str, Any]],
    body: Callable[[AsyncClientSession], Awaitable[T]],
) -> T:
    """Run `body` in one transaction, retrying on transient errors and unknown commit results.

    `body` may run more than once, so it must have no side effects outside Mongo.
    """
    async with client.start_session() as session:
        return await session.with_transaction(body)


async def ensure_processed_events(db: AsyncDatabase[dict[str, Any]]) -> None:
    """The consumer-side half of idempotency (TRD §8.5): `_id` is the event ID."""
    col: AsyncCollection[dict[str, Any]] = db["processed_events"]
    await col.create_index(
        "processed_at",
        expireAfterSeconds=PROCESSED_EVENTS_TTL_DAYS * 86_400,
        name="processed_ttl",
    )
