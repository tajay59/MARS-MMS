"""Migrations under the `_migrations` lock, cron locks, and the relay loop."""

import asyncio
import types

import pytest
from pymongo import AsyncMongoClient

from mms_common import migrations, outbox
from mms_common.cron import run_once_locked
from mms_common.events import Envelope, Resource
from mms_common.mongo import in_transaction
from mms_common.relay import run_relay
from mms_common.time import ManualClock, SystemClock


@pytest.fixture
def migs(monkeypatch):
    """Two migrations, listed out of order, that record their calls."""
    calls: list[str] = []

    def make(name):
        async def up(db):
            await asyncio.sleep(0.05)
            calls.append(name)

        return up

    found = sorted([("0002_b", make("0002_b")), ("0001_a", make("0001_a"))])
    monkeypatch.setattr(migrations, "discover", lambda _: found)
    return types.ModuleType("fake_migrations"), calls


async def test_migrations_run_once_in_order(mongo, migs):
    package, calls = migs
    clock = SystemClock()
    assert await migrations.run(mongo, package, clock) == ["0001_a", "0002_b"]
    assert await migrations.run(mongo, package, clock) == []
    assert calls == ["0001_a", "0002_b"]


async def test_two_instances_starting_together_run_each_migration_once(mongo, migs):
    package, calls = migs
    clock = SystemClock()
    a, b = await asyncio.gather(
        migrations.run(mongo, package, clock, poll_s=0.05),
        migrations.run(mongo, package, clock, poll_s=0.05),
    )
    assert sorted(a + b) == ["0001_a", "0002_b"]
    assert calls == ["0001_a", "0002_b"]
    assert await mongo["_migrations"].find_one({"_id": "lock"}) is None


async def test_an_expired_lock_is_taken_over(mongo, migs):
    package, calls = migs
    clock = ManualClock()
    await mongo["_migrations"].insert_one(
        {"_id": "lock", "owner": "crashed", "expires_at": clock.now()}
    )
    clock.advance(minutes=1)
    assert await migrations.run(mongo, package, clock) == ["0001_a", "0002_b"]


async def test_cron_runs_once_per_interval_across_instances(redis):
    runs = []

    async def job():
        runs.append(1)

    results = await asyncio.gather(
        *[run_once_locked(redis, "svc", "purge", 60, job) for _ in range(5)]
    )
    assert sum(results) == 1
    assert runs == [1]


def event(n: int) -> Envelope:
    from mms_common.ids import new_id

    return Envelope(
        event_id=new_id(), type="user.updated", occurred_at=SystemClock().now(), source="auth",
        key="u1", aggregate_version=n, resource=Resource(type="user", id="u1"),
    )


class FakeProducer:
    def __init__(self, sent, fail_first=0):
        self.sent = sent
        self.fail = fail_first
        self.stopped = False

    async def stop(self):
        self.stopped = True


async def test_relay_loop_survives_kafka_outage_and_keeps_order(mongo_uri, mongo, redis):
    clock = SystemClock()
    client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    db = client[mongo.name]
    col = db["outbox"]
    await outbox.ensure_indexes(col)
    for n in range(1, 4):
        await in_transaction(
            client, lambda s, n=n: outbox.add(col, event(n), session=s, clock=clock)
        )

    sent: list[int] = []
    opened = []

    async def open_producer():
        if len(opened) == 0:
            opened.append("down")
            raise ConnectionError("kafka down")
        producer = FakeProducer(sent)
        opened.append(producer)

        async def produce(topic, key, value):
            import json

            sent.append(json.loads(value)["aggregate_version"])

        return producer, produce

    import mms_common.relay as relay_module

    relay_module.ERROR_BACKOFF_S = 0.1
    lease = outbox.LeaderLease(redis, "svc", "w1")
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_relay(col, lease, open_producer, "mms.svc.events", clock, stop, poll_s=0.05, watch=True)
    )
    for _ in range(100):
        if len(sent) == 3:
            break
        await asyncio.sleep(0.05)
    assert sent == [1, 2, 3]
    # A new row is picked up while running.
    await in_transaction(client, lambda s: outbox.add(col, event(4), session=s, clock=clock))
    for _ in range(100):
        if len(sent) == 4:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await task
    assert sent == [1, 2, 3, 4]
    assert opened[1].stopped
    assert await redis.get("outbox-leader:svc") is None  # released on shutdown
    await client.close()
