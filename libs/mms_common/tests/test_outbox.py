from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mms_common.events import Envelope, Resource
from mms_common.ids import seeded
from mms_common.outbox import LeaderLease, OutboxRelay, add, ensure_indexes, lease_key
from mms_common.time import ManualClock


class FakeLeaseStore:
    """In-memory stand-in for the Redis calls the lease makes."""

    def __init__(self):
        self.owner: str | None = None

    async def set(self, name, value, *, nx, px):
        if self.owner is None:
            self.owner = value
            return True
        return None

    async def eval(self, script, numkeys, key, owner, *rest):
        if self.owner == owner:
            if "del" in script:
                self.owner = None
            return 1
        return 0

    def expire(self):
        self.owner = None


def envelope(ids, n: int, key: str = "r1") -> Envelope:
    return Envelope(
        event_id=ids.new(),
        type="request.approved",
        occurred_at=datetime(2026, 10, 16, tzinfo=UTC),
        source="operations",
        key=key,
        aggregate_version=n,
        resource=Resource(type="request", id=key),
        data={"n": n},
    )


async def test_lease_is_exclusive_and_taken_over_after_expiry():
    store = FakeLeaseStore()
    a, b = LeaderLease(store, "ops", "a"), LeaderLease(store, "ops", "b")
    assert await a.acquire_or_renew() is True
    assert await b.acquire_or_renew() is False
    assert await a.acquire_or_renew() is True  # renew
    store.expire()  # a's lease lapses (a died)
    assert await b.acquire_or_renew() is True
    assert await a.acquire_or_renew() is False  # a must not publish any more
    assert a.held is False


async def test_release_hands_the_lease_over():
    store = FakeLeaseStore()
    a, b = LeaderLease(store, "ops", "a"), LeaderLease(store, "ops", "b")
    await a.acquire_or_renew()
    await a.release()
    assert await b.acquire_or_renew() is True


def test_lease_key_is_per_service():
    assert lease_key("operations") == "outbox-leader:operations"


async def test_add_refuses_to_run_outside_a_transaction(mongo):
    clock = ManualClock()
    async with mongo.client.start_session() as s:
        with pytest.raises(RuntimeError):
            await add(mongo.outbox, envelope(seeded(clock), 1), session=s, clock=clock)


async def test_record_and_event_commit_together(mongo):
    clock = ManualClock()
    ids = seeded(clock)
    await mongo.create_collection("requests")
    await mongo.create_collection("outbox")
    async with mongo.client.start_session() as s, await s.start_transaction():
        await mongo.requests.insert_one({"_id": "r1", "version": 1}, session=s)
        await add(mongo.outbox, envelope(ids, 1), session=s, clock=clock)
    assert await mongo.requests.count_documents({}) == 1
    assert await mongo.outbox.count_documents({"published_at": None}) == 1


async def test_nothing_is_written_when_the_transaction_aborts(mongo):
    clock = ManualClock()
    ids = seeded(clock)
    await mongo.create_collection("requests")
    await mongo.create_collection("outbox")
    with pytest.raises(ZeroDivisionError):
        async with mongo.client.start_session() as s, await s.start_transaction():
            await mongo.requests.insert_one({"_id": "r1"}, session=s)
            await add(mongo.outbox, envelope(ids, 1), session=s, clock=clock)
            1 / 0  # noqa: B018
    assert await mongo.requests.count_documents({}) == 0
    assert await mongo.outbox.count_documents({}) == 0


async def _seed(mongo, clock, ids, n):
    await mongo.create_collection("outbox")
    for i in range(1, n + 1):
        clock.advance(milliseconds=5)
        async with mongo.client.start_session() as s, await s.start_transaction():
            await add(mongo.outbox, envelope(ids, i), session=s, clock=clock)


async def test_relay_publishes_oldest_first_and_marks_rows(mongo):
    clock = ManualClock()
    ids = seeded(clock)
    await _seed(mongo, clock, ids, 3)
    await ensure_indexes(mongo.outbox)
    sent: list[tuple[str, str, int]] = []

    async def produce(topic, key, value):
        sent.append((topic, key, Envelope.model_validate_json(value).aggregate_version))

    lease = LeaderLease(FakeLeaseStore(), "ops", "a")
    relay = OutboxRelay(mongo.outbox, lease, produce, "mms.operations.events", clock)
    assert await relay.run_once() == 3
    assert [v for *_, v in sent] == [1, 2, 3]
    assert sent[0][:2] == ("mms.operations.events", "r1")
    assert await relay.run_once() == 0  # nothing is published twice
    assert await mongo.outbox.count_documents({"published_at": None}) == 0


async def test_a_failed_publish_stops_the_batch_and_is_retried_in_order(mongo):
    clock = ManualClock()
    ids = seeded(clock)
    await _seed(mongo, clock, ids, 3)
    sent: list[int] = []
    fail = {"on": 2}

    async def produce(topic, key, value):
        n = Envelope.model_validate_json(value).aggregate_version
        if n == fail["on"]:
            raise ConnectionError("broker down")
        sent.append(n)

    lease = LeaderLease(FakeLeaseStore(), "ops", "a")
    relay = OutboxRelay(mongo.outbox, lease, produce, "t", clock)
    with pytest.raises(ConnectionError):
        await relay.run_once()
    assert sent == [1]  # 3 did not overtake 2
    fail["on"] = -1
    await relay.run_once()
    assert sent == [1, 2, 3]


async def test_a_follower_publishes_nothing(mongo):
    clock = ManualClock()
    ids = seeded(clock)
    await _seed(mongo, clock, ids, 2)
    store = FakeLeaseStore()
    await LeaderLease(store, "ops", "leader").acquire_or_renew()
    sent: list[int] = []

    async def produce(topic, key, value):
        sent.append(1)

    follower = OutboxRelay(mongo.outbox, LeaderLease(store, "ops", "follower"), produce, "t", clock)
    assert await follower.run_once() == 0
    assert sent == []
