"""Transactional outbox and its relay (TRD §8.2, CLAUDE.md rule 2).

A request handler never produces to Kafka. It updates the record and inserts the outbox
row in ONE Mongo transaction (`add`). The relay publishes later, and only in the process
that holds the service's Redis leader lease, so relays never run in parallel and never
publish out of order.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection

from mms_common.events.envelope import Envelope
from mms_common.time import Clock

LEASE_TTL_MS = 10_000
LEASE_RENEW_S = 3.0
OUTBOX_TTL_DAYS = 7  # published rows are kept for diagnosis only (TRD §8.2)


def lease_key(service: str) -> str:
    return f"outbox-leader:{service}"


class LeaseStore(Protocol):
    """The slice of Redis the lease needs. `redis.asyncio.Redis` satisfies it."""

    async def set(self, name: str, value: str, *, nx: bool, px: int) -> Any: ...
    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...


# Only the holder may renew or release: compare the stored owner first.
_RENEW = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end"
)
_RELEASE = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)


class LeaderLease:
    """`SET NX PX 10000`, renewed every 3 s. Another worker takes over within 10 s."""

    def __init__(self, store: LeaseStore, service: str, owner: str, ttl_ms: int = LEASE_TTL_MS):
        self._store = store
        self._key = lease_key(service)
        self._owner = owner
        self._ttl_ms = ttl_ms
        self.held = False

    async def acquire_or_renew(self) -> bool:
        if self.held:
            renewed = await self._store.eval(_RENEW, 1, self._key, self._owner, self._ttl_ms)
            if renewed:
                return True
            self.held = False  # expired or taken over: fall through and try to acquire
        got = await self._store.set(self._key, self._owner, nx=True, px=self._ttl_ms)
        self.held = bool(got)
        return self.held

    async def release(self) -> None:
        if self.held:
            await self._store.eval(_RELEASE, 1, self._key, self._owner)
            self.held = False


async def add(
    outbox: AsyncCollection[dict[str, Any]],
    envelope: Envelope,
    *,
    session: AsyncClientSession,
    clock: Clock,
) -> None:
    """Insert the event in the caller's transaction. `session` is required on purpose:
    an outbox row written outside the transaction would defeat the pattern."""
    if not session.in_transaction:
        raise RuntimeError("outbox.add must run inside the transaction that changes the record")
    doc = envelope.model_dump(mode="python")
    doc["_id"] = envelope.event_id
    doc["created_at"] = clock.now()
    doc["published_at"] = None
    await outbox.insert_one(doc, session=session)


async def ensure_indexes(outbox: AsyncCollection[dict[str, Any]]) -> None:
    await outbox.create_index([("published_at", 1), ("created_at", 1), ("_id", 1)])
    await outbox.create_index(
        "published_at", expireAfterSeconds=OUTBOX_TTL_DAYS * 86_400, name="published_ttl"
    )


Produce = Callable[[str, str, bytes], Awaitable[None]]
"""`produce(topic, key, value)`. The Kafka producer is idempotent with acks=all (TRD §8.1)."""


class OutboxRelay:
    def __init__(
        self,
        outbox: AsyncCollection[dict[str, Any]],
        lease: LeaderLease,
        produce: Produce,
        topic: str,
        clock: Clock,
        batch_size: int = 100,
    ) -> None:
        self._outbox = outbox
        self._lease = lease
        self._produce = produce
        self._topic = topic
        self._clock = clock
        self._batch = batch_size

    async def run_once(self) -> int:
        """Publish pending events, oldest first. Returns how many were published.

        Stops at the first failure so a later event never overtakes an earlier one
        for the same key. The failed row stays unpublished and is retried next run.
        """
        if not await self._lease.acquire_or_renew():
            return 0
        sent = 0
        cursor = (
            self._outbox.find({"published_at": None})
            .sort([("created_at", 1), ("_id", 1)])
            .limit(self._batch)
        )
        async for row in cursor:
            envelope = Envelope.model_validate(
                {k: v for k, v in row.items() if k not in ("_id", "created_at", "published_at")}
            )
            await self._produce(self._topic, envelope.key, envelope.model_dump_json().encode())
            await self._outbox.update_one(
                {"_id": row["_id"]}, {"$set": {"published_at": self._clock.now()}}
            )
            sent += 1
            if not await self._lease.acquire_or_renew():
                break  # lost the lease mid-batch: stop, the new leader carries on
        return sent
