from __future__ import annotations

from mms_common.ids import seeded
from mms_common.snapshot import MAX_LIMIT, page, upsert_if_newer
from mms_common.time import ManualClock


async def test_pages_cover_every_document_once(mongo):
    ids = seeded(ManualClock())
    docs = [{"_id": ids.new(), "aggregate_version": 1} for _ in range(7)]
    await mongo.users.insert_many(docs)
    seen: list[str] = []
    after = None
    while True:
        result = await page(mongo.users, after=after, limit=3)
        seen += [d["_id"] for d in result.items]
        after = result.next_after
        if after is None:
            break
    assert seen == [d["_id"] for d in docs]


async def test_limit_is_capped(mongo):
    result = await page(mongo.users, limit=10_000)
    assert result.items == [] and result.next_after is None
    assert MAX_LIMIT == 500


async def test_newer_version_replaces_older_is_ignored(mongo):
    assert await upsert_if_newer(mongo.rm, {"_id": "a", "aggregate_version": 2, "v": "two"})
    assert await upsert_if_newer(mongo.rm, {"_id": "a", "aggregate_version": 3, "v": "three"})
    assert not await upsert_if_newer(mongo.rm, {"_id": "a", "aggregate_version": 2, "v": "old"})
    assert not await upsert_if_newer(mongo.rm, {"_id": "a", "aggregate_version": 3, "v": "same"})
    assert (await mongo.rm.find_one({"_id": "a"}))["v"] == "three"


async def test_snapshot_and_event_converge_in_either_order(mongo):
    event = {"_id": "x", "aggregate_version": 5, "v": "event"}
    snap = {"_id": "x", "aggregate_version": 4, "v": "snapshot"}
    await upsert_if_newer(mongo.a, event)
    await upsert_if_newer(mongo.a, snap)
    await upsert_if_newer(mongo.b, snap)
    await upsert_if_newer(mongo.b, event)
    assert (await mongo.a.find_one({"_id": "x"}))["v"] == "event"
    assert (await mongo.b.find_one({"_id": "x"}))["v"] == "event"


async def test_a_stale_version_inside_a_transaction_leaves_it_usable(mongo):
    """A consumer applies events in a transaction (TRD §8.5). A late, older event must be
    skipped without aborting it: the write after it still commits."""
    from mms_common.mongo import in_transaction

    await upsert_if_newer(mongo.rm, {"_id": "a", "aggregate_version": 3, "v": "three"})

    async def body(session):
        written = await upsert_if_newer(
            mongo.rm, {"_id": "a", "aggregate_version": 2, "v": "old"}, session=session
        )
        await mongo.other.insert_one({"_id": "after"}, session=session)
        return written

    assert await in_transaction(mongo.client, body) is False
    assert await mongo.other.find_one({"_id": "after"}) is not None
    assert (await mongo.rm.find_one({"_id": "a"}))["v"] == "three"
