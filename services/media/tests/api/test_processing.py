"""What happens after the last part: size, type, checksum and virus checks, and the cron jobs
that rescue uploads that stall (PRD MED-3; TRD §3.3)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from mms_common.ids import new_id

from app.domain.media import ScanStatus
from app.jobs import cron
from app.jobs.process import Retry, process_media
from tests.conftest import PDF, STATION, sha256


async def uploaded(media, data=PDF, **kw):
    out = await media.upload(data, **kw)
    return out["media_id"]


@pytest.mark.req("MED-3")
async def test_a_clean_file_becomes_ready_and_says_so(media):
    media_id = await uploaded(media)
    assert await process_media(media.svc, media_id) == "ready"
    record = await media.record(media_id)
    assert record["status"] == "ready"
    assert record["scan_status"] == "clean"
    assert record["processed_key"] == record["original_key"]
    [event] = await media.outbox("media.processed")
    assert event.data["scan_status"] == "clean"
    assert event.data["checksum_sha256"] == sha256(PDF)


async def test_a_host_without_a_scanner_says_the_file_was_not_scanned(media):
    media.scanner.status = ScanStatus.SKIPPED  # staging, where ClamAV doesn't fit (T8)
    media_id = await uploaded(media)
    await process_media(media.svc, media_id)
    assert (await media.record(media_id))["scan_status"] == "skipped"
    [event] = await media.outbox("media.processed")
    assert event.data["scan_status"] == "skipped"


async def test_processing_twice_does_nothing_the_second_time(media):
    media_id = await uploaded(media)
    assert await process_media(media.svc, media_id) == "ready"
    assert await process_media(media.svc, media_id) == "skipped"
    assert len(await media.outbox("media.processed")) == 1


@pytest.mark.req("MED-3")
async def test_an_infected_file_is_failed_and_removed_from_the_store(media):
    media.scanner.infected = True
    media_id = await uploaded(media)
    record = await media.record(media_id)
    assert await process_media(media.svc, media_id) == "failed"
    assert (await media.record(media_id))["error"] == "infected"
    assert not media.object_exists(record)
    [event] = await media.outbox("media.failed")
    assert event.data["reason"] == "infected"


async def test_a_file_that_is_not_what_its_name_says_is_failed(media):
    data = b"this is not a pdf at all"
    media_id = await uploaded(media, data)
    assert await process_media(media.svc, media_id) == "failed"
    assert (await media.record(media_id))["error"] == "bad_type"


async def test_a_wrong_checksum_is_failed(media):
    data = PDF
    created = await media.create(data, sha=sha256(b"something else"))
    body = created.json()
    await media.put_all(body, data)
    await media.complete(body["media_id"])
    assert await process_media(media.svc, body["media_id"]) == "failed"
    assert (await media.record(body["media_id"]))["error"] == "checksum_mismatch"


async def test_a_config_file_may_be_binary_but_is_still_scanned(media):
    data = bytes(range(256)) * 4
    media_id = await uploaded(media, data, kind="config", filename="program.cr1000x",
                              owner_ref=f"config:{STATION}")
    media.scanner.infected = True
    assert await process_media(media.svc, media_id) == "failed"


async def test_a_scanner_that_is_down_puts_the_file_back_and_never_releases_it(media):
    media.scanner.down = True
    media_id = await uploaded(media)
    with pytest.raises(Retry):
        await process_media(media.svc, media_id)
    assert (await media.record(media_id))["status"] == "uploaded"
    media.scanner.down = False
    assert await process_media(media.svc, media_id) == "ready"


async def test_reconcile_queues_files_that_wait_too_long(media):
    media_id = await uploaded(media)
    media.jobs.queued.clear()
    assert await cron.reconcile(media.svc) == 0  # just uploaded: give the queue time
    media.clock.advance(minutes=16)
    assert await cron.reconcile(media.svc) == 1
    assert media.jobs.queued == [media_id]


async def test_reconcile_puts_back_a_file_whose_worker_died(media):
    media_id = await uploaded(media)
    await media.db["media"].update_one({"_id": media_id}, {"$set": {"status": "processing"}})
    media.clock.advance(minutes=31)
    media.jobs.queued.clear()
    await media.db["media"].update_one(
        {"_id": media_id}, {"$set": {"updated_at": media.clock.now() - timedelta(minutes=31)}}
    )
    assert await cron.reconcile(media.svc) == 1
    assert (await media.record(media_id))["status"] == "uploaded"
    assert media.jobs.queued == [media_id]


async def test_stale_uploads_are_aborted_and_marked_failed(media):
    body = (await media.create()).json()
    fresh = (await media.create(PDF + b"different")).json()  # the same file would resume
    record = await media.record(body["media_id"])
    media.clock.advance(hours=49)
    await media.db["media"].update_one(
        {"_id": fresh["media_id"]}, {"$set": {"updated_at": media.clock.now()}}
    )
    assert await cron.abort_stale_uploads(media.svc) == 1
    stale = await media.record(body["media_id"])
    assert stale["status"] == "failed" and stale["error"] == "stale"
    found = media.s3.list_multipart_uploads(
        Bucket=media.settings.bucket_documents, Prefix=record["original_key"]
    )
    assert found.get("Uploads", []) == []
    assert (await media.record(fresh["media_id"]))["status"] == "pending"
    [event] = await media.outbox("media.failed")
    assert event.data["reason"] == "stale"


async def test_an_unknown_file_is_ignored(media):
    assert await process_media(media.svc, new_id()) == "skipped"
