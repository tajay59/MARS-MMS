"""Photos and video through the whole pipeline on real SeaweedFS (PRD MED-1, MED-2, MED-4, MED-5,
MED-7; TRD §3.3, §10): upload, checks, the copy people look at, who may see what, and the purge
of originals after 30 days. Video needs ffmpeg and is skipped where it is missing."""

from __future__ import annotations

import io
from datetime import datetime

import pytest
from PIL import Image

from app.jobs import cron
from app.jobs.process import process_media
from tests.media_files import ffmpeg_available, has_exif_or_gps, jpeg, video

needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed here")
TAKEN = datetime(2026, 10, 21, 8, 30, 15)  # noqa: DTZ001


def bucket(media, name: str) -> str:
    return str(getattr(media.settings, f"bucket_{name}"))


def stored(media, name: str, key: str) -> bytes:
    body: bytes = media.s3.get_object(Bucket=bucket(media, name), Key=key)["Body"].read()
    return body


def exists(media, name: str, key: str) -> bool:
    try:
        media.s3.head_object(Bucket=bucket(media, name), Key=key)
    except Exception:  # noqa: BLE001
        return False
    return True


async def photo(media, data: bytes | None = None, **kw):
    """A photo uploaded and completed; returns its id."""
    data = data or jpeg((3000, 2000), gps=True, taken=TAKEN, offset="-05:00", orientation=1)
    out = await media.upload(data, kind="image", filename="IMG_0001.JPG", **kw)
    return out["media_id"], data


async def share(media, media_id: str) -> None:
    """The owning service shares the file with the organization (ADR-19)."""
    await media.db["media"].update_one({"_id": media_id}, {"$set": {"visibility": "org"}})


@pytest.mark.req("MED-1")
@pytest.mark.req("MED-7")
async def test_a_photo_is_processed_into_a_clean_copy_and_a_thumbnail(media):
    media_id, original = await photo(media)
    assert await process_media(media.svc, media_id) == "ready"
    record = await media.record(media_id)
    assert record["status"] == "ready" and record["scan_status"] == "clean"
    assert (record["width"], record["height"]) == (2048, 1365)
    assert record["processed_key"].endswith("/view.webp")
    assert record["thumbnail_key"].endswith("/thumb.webp")
    assert record["captured_at"] == datetime(2026, 10, 21, 13, 30, 15)  # UTC, from the EXIF offset
    assert record["ready_at"] is not None and record["original_purged_at"] is None
    view = stored(media, "media", record["processed_key"])
    thumb = stored(media, "media", record["thumbnail_key"])
    assert Image.open(io.BytesIO(view)).format == "WEBP"
    assert Image.open(io.BytesIO(thumb)).size[0] == 400
    assert not has_exif_or_gps(view) and not has_exif_or_gps(thumb)
    # the original is kept untouched until the purge
    assert stored(media, "originals", record["original_key"]) == original


@pytest.mark.req("MED-1")
async def test_the_ready_event_carries_the_size_and_the_capture_time(media):
    media_id, _ = await photo(media)
    await process_media(media.svc, media_id)
    [event] = await media.outbox("media.processed")
    assert (event.data["width"], event.data["height"]) == (2048, 1365)
    assert event.data["duration_s"] is None
    assert event.data["captured_at"].startswith("2026-10-21T13:30:15")


@pytest.mark.req("MED-4")
async def test_staff_get_the_copy_the_thumbnail_and_the_original(media):
    media_id, original = await photo(media)
    await process_media(media.svc, media_id)
    got = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("tech1"))
    assert got.status_code == 200, got.text
    body = got.json()
    assert set(body["urls"]) == {"view", "thumbnail", "original"}
    assert (body["width"], body["height"]) == (2048, 1365)
    view = await media.store.get(body["urls"]["view"])
    assert view.status_code == 200 and view.headers["content-type"] == "image/webp"
    assert not has_exif_or_gps(view.content)
    kept = await media.store.get(body["urls"]["original"])
    assert kept.content == original  # staff can still reach the original
    assert "attachment" in kept.headers["content-disposition"]


@pytest.mark.req("MED-4")
async def test_a_client_sees_a_shared_photo_but_never_its_original(media):
    media_id, _ = await photo(media)
    await process_media(media.svc, media_id)
    hidden = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_a1"))
    assert hidden.status_code == 404  # staff only until the owner shares it
    await share(media, media_id)
    shown = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_a1"))
    assert shown.status_code == 200
    assert set(shown.json()["urls"]) == {"view", "thumbnail"}
    other = await media.http.get(f"/api/v1/media/{media_id}", headers=media.bearer("client_b1"))
    assert other.status_code == 404


@pytest.mark.req("MED-3")
async def test_a_photo_that_will_not_open_fails_and_its_original_is_kept(media):
    # The right first bytes, then nothing a decoder can use
    broken = jpeg((800, 600))[:300] + b"\x00" * 200
    media_id, _ = await photo(media, broken)
    assert await process_media(media.svc, media_id) == "failed"
    record = await media.record(media_id)
    assert record["error"] == "unreadable_image"
    assert exists(media, "originals", record["original_key"])  # a site photo may not be retakeable
    assert not exists(media, "media", record["original_key"].rsplit("/", 1)[0] + "/view.webp")
    [event] = await media.outbox("media.failed")
    assert event.data["reason"] == "unreadable_image"
    assert (await media.http.get(f"/api/v1/media/{media_id}",
                                 headers=media.bearer("tech1"))).json()["urls"] == {}


@pytest.mark.req("MED-3")
async def test_a_png_called_jpg_is_refused_and_removed(media):
    from tests.media_files import png

    media_id, _ = await photo(media, png())
    assert await process_media(media.svc, media_id) == "failed"
    record = await media.record(media_id)
    assert record["error"] == "bad_type"
    assert not exists(media, "originals", record["original_key"])


@pytest.mark.req("MED-3")
async def test_a_virus_in_a_photo_is_failed_and_removed(media):
    media.scanner.infected = True
    media_id, _ = await photo(media)
    assert await process_media(media.svc, media_id) == "failed"
    record = await media.record(media_id)
    assert record["error"] == "infected"
    assert not exists(media, "originals", record["original_key"])
    assert record.get("thumbnail_key") is None


async def test_processing_a_photo_twice_makes_one_copy_and_one_event(media):
    media_id, _ = await photo(media)
    assert await process_media(media.svc, media_id) == "ready"
    assert await process_media(media.svc, media_id) == "skipped"
    assert len(await media.outbox("media.processed")) == 1


@pytest.mark.req("MED-1")
async def test_originals_are_purged_after_thirty_days_and_the_copy_stays(media):
    media_id, _ = await photo(media)
    await process_media(media.svc, media_id)
    record = await media.record(media_id)

    media.clock.advance(days=29)
    assert await cron.purge_originals(media.svc) == 0
    assert exists(media, "originals", record["original_key"])

    media.clock.advance(days=2)
    assert await cron.purge_originals(media.svc) == 1
    assert not exists(media, "originals", record["original_key"])
    assert (await media.record(media_id))["original_purged_at"] is not None
    assert exists(media, "media", record["processed_key"])  # the copy people look at stays
    assert await cron.purge_originals(media.svc) == 0  # once

    urls = (await media.http.get(f"/api/v1/media/{media_id}",
                                 headers=media.bearer("tech1"))).json()["urls"]
    assert set(urls) == {"view", "thumbnail"}  # no original to offer


async def test_a_document_is_never_purged_or_given_a_thumbnail(media):
    out = await media.upload()  # a PDF
    await process_media(media.svc, out["media_id"])
    media.clock.advance(days=90)
    assert await cron.purge_originals(media.svc) == 0
    record = await media.record(out["media_id"])
    assert record.get("thumbnail_key") is None and record["processed_key"] == record["original_key"]
    got = await media.http.get(f"/api/v1/media/{out['media_id']}", headers=media.bearer("tech1"))
    assert set(got.json()["urls"]) == {"view", "download"}  # as before: documents are unchanged


# --- Video (needs ffmpeg) -----------------------------------------------------------------------


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_a_phone_video_is_processed_into_a_playable_mp4_with_a_poster(media, tmp_path):
    data = video(tmp_path / "VID_1.mp4", seconds=3, size="1920x1080").read_bytes()
    out = await media.upload(data, kind="video", filename="VID_1.MP4")
    assert await process_media(media.svc, out["media_id"]) == "ready"
    record = await media.record(out["media_id"])
    assert (record["width"], record["height"]) == (1280, 720)
    assert 2.5 <= record["duration_s"] <= 3.5
    assert record["processed_key"].endswith("/view.mp4")
    assert record["processed_size_bytes"] == len(stored(media, "media", record["processed_key"]))
    assert Image.open(io.BytesIO(stored(media, "media", record["thumbnail_key"]))).format == "WEBP"
    [event] = await media.outbox("media.processed")
    assert event.data["duration_s"] == record["duration_s"] and event.data["width"] == 1280
    got = (await media.http.get(f"/api/v1/media/{out['media_id']}",
                                headers=media.bearer("tech1"))).json()
    played = await media.store.get(got["urls"]["view"])
    assert played.headers["content-type"] == "video/mp4"
    assert played.content[4:8] == b"ftyp"
    assert stored(media, "originals", record["original_key"]) == data


@needs_ffmpeg
@pytest.mark.req("MED-3")
async def test_a_video_that_will_not_open_fails_with_a_reason_and_keeps_its_original(media):
    junk = b"\x00\x00\x00\x18ftypmp42" + b"this is not a video" * 200
    out = await media.upload(junk, kind="video", filename="VID_2.mp4")
    assert await process_media(media.svc, out["media_id"]) == "failed"
    record = await media.record(out["media_id"])
    assert record["error"] in ("unreadable_video", "no_video_stream")
    assert exists(media, "originals", record["original_key"])


async def test_a_host_without_ffmpeg_puts_the_video_back_to_try_again(media, monkeypatch):
    from app.jobs.process import Retry

    monkeypatch.setenv("PATH", "")
    data = b"\x00\x00\x00\x18ftypmp42" + b"x" * 2000
    out = await media.upload(data, kind="video", filename="VID_3.mp4")
    with pytest.raises(Retry):
        await process_media(media.svc, out["media_id"])
    assert (await media.record(out["media_id"]))["status"] == "uploaded"
