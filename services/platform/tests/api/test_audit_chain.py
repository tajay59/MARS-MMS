"""The audit chain on a real MongoDB replica set (TRD §12; TP "Audit insert-only and chain",
"Event backbone": duplicates, concurrency; AUD-1, AUD-2, AUD-3, AUD-5)."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from mms_common import migrations, mongo
from mms_common.consumer import Outcome
from mms_common.events import Actor, Envelope, Resource
from mms_common.ids import new_id
from mms_common.time import ManualClock

from app.events.audit_consumer import processor
from app.migrations import audit as audit_migrations
from app.repo.audit import verify


@pytest_asyncio.fixture
async def audit(mongo_uri):
    client = mongo.connect(mongo_uri)
    db = client[f"audit_{uuid.uuid4().hex[:8]}"]
    clock = ManualClock(datetime(2026, 10, 17, 9, tzinfo=UTC))
    await migrations.run(db, audit_migrations, clock)
    dead: list[tuple[bytes, str]] = []

    async def to_dlq(raw: bytes, reason: str) -> None:
        dead.append((raw, reason))

    async def no_sleep(_: float) -> None:
        return None

    proc = processor(client, db, to_dlq, clock)
    proc._sleep = no_sleep  # retries without waiting
    yield proc, db, dead, clock
    await client.drop_database(db.name)
    await client.close()


def event(type_="auth.login_succeeded", data=None, **extra) -> bytes:
    user = "01900000-0000-7000-8000-000000000071"
    envelope = Envelope(
        event_id=new_id(),
        type=type_,
        occurred_at=datetime(2026, 10, 17, 9, 0, 0, 123456, tzinfo=UTC),
        source="auth",
        key=user,
        aggregate_version=3,
        actor=Actor(user_id=user, name="Tech 1", roles=["technician"], ip="203.0.113.9",
                    user_agent="Phone", device_id="dev-1"),
        resource=Resource(type="user", id=user),
        correlation_id="req-1",
        data=data if data is not None else {"user_id": user, "email_hash": "ab" * 32},
        **extra,
    )
    return envelope.model_dump_json().encode()


@pytest.mark.req("AUD-2")
async def test_each_event_becomes_a_chained_record(audit):
    proc, db, _, _ = audit
    for _ in range(3):
        assert await proc.process(event()) is Outcome.APPLIED
    records = [r async for r in db["audit_events"].find().sort("seq", 1)]
    assert [r["seq"] for r in records] == [1, 2, 3]
    assert records[0]["prev_hash"] == "0" * 64
    assert records[1]["prev_hash"] == records[0]["hash"]
    first = records[0]
    assert first["action"] == "auth.login_succeeded"
    assert first["actor"] == {"user_id": "01900000-0000-7000-8000-000000000071", "name": "Tech 1",
                              "roles": ["technician"], "ip": "203.0.113.9",
                              "user_agent": "Phone", "device_id": "dev-1"}
    assert first["resource"]["type"] == "user" and first["correlation_id"] == "req-1"
    assert first["source_service"] == "auth"
    state = await db["audit_state"].find_one({"_id": "chain"})
    assert (state["last_seq"], state["last_hash"]) == (3, records[-1]["hash"])
    assert await verify(db) is None


@pytest.mark.req("AUD-1")
async def test_before_and_after_are_kept(audit):
    proc, db, _, _ = audit
    raw = event("user.disabled", data={"user_id": "u", "email": "t@x.org", "name": "T",
                                       "roles": ["technician"], "status": "disabled"},
                audit={"before": {"status": "active"}, "after": {"status": "disabled"}})
    assert await proc.process(raw) is Outcome.APPLIED
    record = await db["audit_events"].find_one()
    assert (record["before"], record["after"]) == ({"status": "active"}, {"status": "disabled"})


async def test_a_duplicate_delivery_is_recorded_once(audit):
    proc, db, _, _ = audit
    raw = event()
    assert await proc.process(raw) is Outcome.APPLIED
    assert await proc.process(raw) is Outcome.DUPLICATE
    assert await db["audit_events"].count_documents({}) == 1


async def test_concurrent_writers_never_share_a_seq(audit):
    """Two workers in the audit group append at once: the chain stays one line."""
    proc, db, _, _ = audit
    outcomes = await asyncio.gather(*(proc.process(event()) for _ in range(20)))
    assert set(outcomes) == {Outcome.APPLIED}
    seqs = [r["seq"] async for r in db["audit_events"].find().sort("seq", 1)]
    assert seqs == list(range(1, 21))
    assert await verify(db) is None


@pytest.mark.req("AUD-5")
async def test_editing_a_stored_record_is_detected(audit, mongo_uri):
    """TP: editing one record directly (here as root, since the audit user can't) makes the
    integrity check report that record."""
    proc, db, _, _ = audit
    for _ in range(5):
        await proc.process(event())
    root = mongo.connect(mongo_uri)
    await root[db.name]["audit_events"].update_one({"seq": 3}, {"$set": {"actor.ip": "10.0.0.1"}})
    assert await verify(db) == 3
    assert await verify(db, 1, 2) is None
    await root.close()


@pytest.mark.req("AUD-5")
async def test_deleting_the_newest_record_is_detected(audit, mongo_uri):
    proc, db, _, _ = audit
    for _ in range(3):
        await proc.process(event())
    root = mongo.connect(mongo_uri)
    await root[db.name]["audit_events"].delete_one({"seq": 3})
    assert await verify(db) == 3
    await root[db.name]["audit_events"].delete_one({"seq": 2})
    assert await verify(db) == 2
    await root.close()


async def test_notification_only_events_are_not_audited(audit):
    proc, db, _, _ = audit
    data = {
        "request_id": "r", "ref": "MR-2026-0001", "org_id": "o", "station_ids": ["s"],
        "category": "fault", "priority": "normal", "status": "client_review", "day": 7.0,
        "auto_close_day": 30.0,
    }
    raw = event("request.review_reminder", data=data)
    assert await proc.process(raw) is Outcome.APPLIED
    assert await db["audit_events"].count_documents({}) == 0


async def test_unknown_events_go_to_the_dead_letter_topic(audit):
    proc, db, dead, _ = audit
    assert await proc.process(event("nobody.knows")) is Outcome.DEAD_LETTERED
    assert await proc.process(b"not json") is Outcome.DEAD_LETTERED
    assert len(dead) == 2
    assert await db["audit_events"].count_documents({}) == 0


async def test_times_are_stored_to_the_millisecond_and_still_verify(audit):
    proc, db, _, _ = audit
    await proc.process(event())
    record = await db["audit_events"].find_one()
    assert record["at"].microsecond == 123000
    assert await verify(db) is None


async def test_an_empty_head_without_a_hash_starts_from_genesis(audit):
    """A head left as {last_seq: 0} (an old probe) must not block the chain."""
    proc, db, _, _ = audit
    await db["audit_state"].replace_one({"_id": "chain"}, {"_id": "chain", "last_seq": 0})
    assert await proc.process(event()) is Outcome.APPLIED
    assert (await db["audit_events"].find_one())["prev_hash"] == "0" * 64
