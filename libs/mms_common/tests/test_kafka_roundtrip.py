"""End to end through a real broker: a record and its event commit in one transaction, the
relay publishes under the lease, and a consumer applies it exactly once (TRD §8.2, §8.5)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from mms_common.consumer import EventProcessor
from mms_common.events import SCHEMAS, Envelope, Resource, register
from mms_common.ids import seeded
from mms_common.kafka import producer_fn, run_consumer, start_producer, topic_for
from mms_common.outbox import LeaderLease, OutboxRelay, add
from mms_common.time import ManualClock


@pytest.fixture(autouse=True)
def _schema():
    before = dict(SCHEMAS)

    @register("request.approved")
    class Approved(BaseModel):
        request_id: str

    yield
    SCHEMAS.clear()
    SCHEMAS.update(before)


async def wait_for(predicate, seconds: float = 30) -> None:
    for _ in range(int(seconds * 10)):
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError("condition not met")


async def test_outbox_to_kafka_to_consumer(mongo_uri, redis_url, kafka_bootstrap):
    bootstrap, create_topic = kafka_bootstrap
    service = f"rt{uuid.uuid4().hex[:6]}"
    topic = topic_for(service)
    create_topic(topic)

    clock = ManualClock(datetime(2026, 10, 17, tzinfo=UTC))
    ids = seeded(clock)
    client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    producer_db = client[f"{service}_producer"]
    consumer_db = client[f"{service}_consumer"]
    for db, names in ((producer_db, ["requests", "outbox"]),
                      (consumer_db, ["processed_events", "read_model"])):
        for name in names:
            await db.create_collection(name)
    redis = Redis.from_url(redis_url)
    producer = await start_producer(bootstrap, client_id=service)

    try:
        # Producer side: three approvals, each a record change plus its outbox row.
        request_ids = [ids.new() for _ in range(3)]
        for n, rid in enumerate(request_ids, start=1):
            clock.advance(milliseconds=10)
            async with client.start_session() as s, await s.start_transaction():
                await producer_db.requests.insert_one({"_id": rid, "version": 1}, session=s)
                await add(producer_db.outbox, Envelope(
                    event_id=ids.new(), type="request.approved", occurred_at=clock.now(),
                    source=service, key=rid, aggregate_version=n,
                    resource=Resource(type="request", id=rid), data={"request_id": rid},
                ), session=s, clock=clock)

        relay = OutboxRelay(producer_db.outbox, LeaderLease(redis, service, "w1"),
                            producer_fn(producer), topic, clock)
        follower = OutboxRelay(producer_db.outbox, LeaderLease(redis, service, "w2"),
                               producer_fn(producer), topic, clock)
        assert await relay.run_once() == 3
        assert await follower.run_once() == 0  # never two relays at once
        assert await relay.run_once() == 0  # nothing published twice

        # Consumer side: apply each event to a read model, in the handler's transaction.
        dlq: list[str] = []

        async def handler(payload, envelope, session):
            await consumer_db.read_model.insert_one(
                {"_id": payload.request_id, "aggregate_version": envelope.aggregate_version},
                session=session,
            )

        async def to_dlq(raw, reason):
            dlq.append(reason)

        processor = EventProcessor(client, consumer_db, {"request.approved": handler},
                                   to_dlq, clock)
        task = asyncio.create_task(run_consumer(bootstrap, f"{service}-group", [topic], processor))
        try:
            async def all_applied() -> bool:
                return await consumer_db.read_model.count_documents({}) == 3

            await wait_for(all_applied)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        # A redelivery (a consumer restarting before its commit landed) changes nothing.
        raw = Envelope.model_validate(
            {k: v for k, v in (await producer_db.outbox.find_one({})).items()
             if k not in ("_id", "created_at", "published_at")}
        ).model_dump_json().encode()
        await processor.process(raw)
        assert await consumer_db.read_model.count_documents({}) == 3
        assert await consumer_db.processed_events.count_documents({}) == 3
        assert dlq == []
        applied = [d["_id"] async for d in consumer_db.read_model.find()]
        assert sorted(applied) == sorted(request_ids)
    finally:
        await producer.stop()
        await redis.aclose()
        await client.drop_database(producer_db.name)
        await client.drop_database(consumer_db.name)
        await client.close()
