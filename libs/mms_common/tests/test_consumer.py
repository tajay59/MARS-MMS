from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from mms_common.consumer import MAX_ATTEMPTS, EventProcessor, Outcome
from mms_common.events import SCHEMAS, Envelope, Resource, register
from mms_common.ids import seeded
from mms_common.time import ManualClock


@pytest.fixture(autouse=True)
def _schema():
    before = dict(SCHEMAS)

    @register("thing.happened")
    class Happened(BaseModel):
        n: int

    yield
    SCHEMAS.clear()
    SCHEMAS.update(before)


def raw(ids, type_="thing.happened", data=None) -> bytes:
    return Envelope(
        event_id=ids.new(),
        type=type_,
        occurred_at=datetime(2026, 10, 16, tzinfo=UTC),
        source="ops",
        key="k",
        aggregate_version=1,
        resource=Resource(type="thing", id="k"),
        data={"n": 1} if data is None else data,
    ).model_dump_json().encode()


class Rig:
    def __init__(self, mongo):
        self.clock = ManualClock()
        self.ids = seeded(self.clock)
        self.dlq: list[str] = []
        self.sleeps: list[float] = []
        self.calls = 0
        self.fail_times = 0

        async def handler(payload, envelope, session):
            self.calls += 1
            await mongo["effects"].insert_one({"_id": envelope.event_id}, session=session)
            if self.calls <= self.fail_times:
                raise RuntimeError("transient")

        async def dlq(message, reason):
            self.dlq.append(reason)

        async def sleep(s):
            self.sleeps.append(s)

        self.processor = EventProcessor(
            mongo.client, mongo, {"thing.happened": handler}, dlq, self.clock, sleep
        )


@pytest.fixture
async def rig(mongo):
    for name in ("effects", "processed_events"):
        await mongo.create_collection(name)
    return Rig(mongo)


async def test_applies_once_and_ignores_a_redelivery(rig, mongo):
    message = raw(rig.ids)
    assert await rig.processor.process(message) is Outcome.APPLIED
    assert await rig.processor.process(message) is Outcome.DUPLICATE
    assert rig.calls == 1
    assert await mongo.effects.count_documents({}) == 1


async def test_unknown_type_goes_straight_to_the_dlq(rig):
    assert await rig.processor.process(raw(rig.ids, type_="nope.never")) is Outcome.DEAD_LETTERED
    assert rig.calls == 0 and len(rig.dlq) == 1


async def test_invalid_payload_goes_straight_to_the_dlq(rig):
    assert await rig.processor.process(raw(rig.ids, data={})) is Outcome.DEAD_LETTERED
    assert rig.calls == 0


async def test_garbage_goes_to_the_dlq(rig):
    assert await rig.processor.process(b"not json") is Outcome.DEAD_LETTERED


async def test_transient_failure_retries_with_backoff_and_rolls_back(rig, mongo):
    rig.fail_times = 2
    assert await rig.processor.process(raw(rig.ids)) is Outcome.APPLIED
    assert rig.calls == 3
    assert rig.sleeps == [1.0, 2.0]
    # Each failed attempt rolled back its processed_events row and effect together.
    assert await mongo.effects.count_documents({}) == 1
    assert await mongo.processed_events.count_documents({}) == 1


async def test_persistent_failure_is_dead_lettered_after_five_attempts(rig, mongo):
    rig.fail_times = 99
    assert await rig.processor.process(raw(rig.ids)) is Outcome.DEAD_LETTERED
    assert rig.calls == MAX_ATTEMPTS
    assert rig.sleeps == [1.0, 2.0, 4.0, 8.0]
    assert "failed after 5 attempts" in rig.dlq[0]
    assert await mongo.processed_events.count_documents({}) == 0  # may be redriven later


async def test_event_types_without_a_handler_are_skipped(rig):
    @register("other.happened")
    class Other(BaseModel):
        pass

    message = raw(rig.ids, type_="other.happened", data={})
    assert await rig.processor.process(message) is Outcome.APPLIED
    assert rig.calls == 0
