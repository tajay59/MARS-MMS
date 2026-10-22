"""Photos and video made into the copy people look at (PRD MED-1, MED-2, MED-5, MED-7; TRD §10),
on files made at test time. The video tests need ffmpeg and are skipped where it is missing (CI
installs it; the media image carries it)."""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from app.domain import derive
from app.domain.media import Kind
from app.repo import render
from tests.media_files import ffmpeg_available, has_exif_or_gps, heic, jpeg, png, video

TAKEN = datetime(2026, 10, 21, 8, 30, 15)  # noqa: DTZ001 - a wall clock, as a camera writes it


def write(tmp_path: Path, data: bytes, name: str = "photo.jpg") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# --- Photos --------------------------------------------------------------------------------------


@pytest.mark.req("MED-1")
def test_a_photo_becomes_a_webp_no_wider_than_2048_with_a_400_thumbnail(tmp_path):
    result = render.render_image(write(tmp_path, jpeg((4000, 3000))))
    assert opened(result.view).format == "WEBP"
    assert (result.width, result.height) == (2048, 1536)
    assert opened(result.view).size == (2048, 1536)
    assert opened(result.thumb).size == (400, 300)
    assert len(result.view) < len(jpeg((4000, 3000)))  # smaller, not just resized


@pytest.mark.req("MED-1")
def test_a_small_photo_is_not_enlarged(tmp_path):
    result = render.render_image(write(tmp_path, jpeg((320, 240))))
    assert (result.width, result.height) == (320, 240)
    assert opened(result.thumb).size == (320, 240)


@pytest.mark.req("MED-7")
def test_gps_exif_and_the_camera_are_removed_from_the_copy_and_the_thumbnail(tmp_path):
    original = jpeg((800, 600), gps=True, taken=TAKEN, offset="-05:00", orientation=1)
    assert has_exif_or_gps(original)  # the test file really carries them
    result = render.render_image(write(tmp_path, original))
    assert not has_exif_or_gps(result.view)
    assert not has_exif_or_gps(result.thumb)


@pytest.mark.req("MED-1")
def test_a_photo_taken_sideways_is_turned_upright(tmp_path):
    result = render.render_image(write(tmp_path, jpeg((800, 600), orientation=6)))
    assert (result.width, result.height) == (600, 800)
    assert not has_exif_or_gps(result.view)  # the orientation flag is gone: the pixels are turned


@pytest.mark.req("MED-5")
def test_capture_time_is_read_with_its_offset_and_not_guessed_without_one(tmp_path):
    with_offset = render.render_image(write(tmp_path, jpeg(taken=TAKEN, offset="-05:00")))
    assert with_offset.captured_at == datetime(2026, 10, 21, 13, 30, 15, tzinfo=UTC)
    without = render.render_image(write(tmp_path, jpeg(taken=TAKEN), "b.jpg"))
    assert without.captured_at is None  # a wall clock in an unknown zone
    assert render.render_image(write(tmp_path, jpeg(), "c.jpg")).captured_at is None


@pytest.mark.req("MED-1")
def test_a_png_with_transparency_keeps_it(tmp_path):
    result = render.render_image(write(tmp_path, png(alpha=True), "a.png"))
    assert opened(result.view).mode == "RGBA"
    flat = render.render_image(write(tmp_path, png(), "b.png"))
    assert opened(flat.view).mode == "RGB"


@pytest.mark.req("MED-1")
def test_an_iphone_heic_is_read_and_cleaned(tmp_path):
    pytest.importorskip("pillow_heif")
    original = heic((640, 480), gps=True, taken=TAKEN, offset="-05:00")
    result = render.render_image(write(tmp_path, original, "IMG_0001.HEIC"))
    assert opened(result.view).format == "WEBP"
    assert (result.width, result.height) == (640, 480)
    assert not has_exif_or_gps(result.view)


@pytest.mark.req("MED-3")
@pytest.mark.parametrize("data", [
    b"not an image at all",
    jpeg((800, 600))[:200],  # cut off mid-file, as a dropped connection leaves it
    b"",
])
def test_a_file_that_is_not_a_photo_is_unreadable(tmp_path, data):
    with pytest.raises(render.Unreadable) as e:
        render.render_image(write(tmp_path, data))
    assert e.value.code == "unreadable_image"


@pytest.mark.req("MED-3")
def test_a_decompression_bomb_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(render.Unreadable):
        render.render_image(write(tmp_path, jpeg((800, 600))))


def test_the_copy_and_the_thumbnail_are_kept_beside_the_original():
    original = "org-a/document-station/s1/m1/original.jpg"
    assert derive.derived_keys(original, Kind.IMAGE) == (
        "org-a/document-station/s1/m1/view.webp", "org-a/document-station/s1/m1/thumb.webp")
    assert derive.derived_keys("shared/x/y/m2/original.mov", Kind.VIDEO) == (
        "shared/x/y/m2/view.mp4", "shared/x/y/m2/thumb.webp")
    assert derive.view_type("video") == "video/mp4" and derive.view_type("image") == "image/webp"


def test_originals_are_purged_after_thirty_days():
    now = datetime(2026, 11, 30, tzinfo=UTC)
    assert derive.purge_cutoff(now) == datetime(2026, 10, 31, tzinfo=UTC)


# --- Video (needs ffmpeg) -----------------------------------------------------------------------

needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed here")


def streams(path: Path) -> dict:
    out = subprocess.run(  # noqa: S603
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],  # noqa: S607
        check=True, capture_output=True, text=True,
    ).stdout
    found: dict = json.loads(out)
    return found


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_a_1080p_phone_video_becomes_a_720p_h264_aac_mp4_that_plays_everywhere(tmp_path):
    source = video(tmp_path / "in.mp4", size="1920x1080")
    out = tmp_path / "out.mp4"
    await render.transcode_video(source, out, threads=2, timeout_s=120)
    info = await render.probe_video(out)
    assert (info.width, info.height) == (1280, 720)
    assert info.duration_s is not None and 2.5 <= info.duration_s <= 3.5
    found = {s["codec_type"]: s for s in streams(out)["streams"]}
    assert found["video"]["codec_name"] == "h264" and found["video"]["pix_fmt"] == "yuv420p"
    assert found["audio"]["codec_name"] == "aac"
    # the index is at the front, so it starts playing before it has all arrived (+faststart)
    head = out.read_bytes()[:4096]
    assert b"moov" in head
    assert b"mdat" not in head or head.find(b"moov") < head.find(b"mdat")


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_a_small_video_is_not_enlarged_and_one_without_sound_is_fine(tmp_path):
    source = video(tmp_path / "in.mp4", size="640x360", audio=False)
    out = tmp_path / "out.mp4"
    await render.transcode_video(source, out, threads=2, timeout_s=120)
    info = await render.probe_video(out)
    assert (info.width, info.height) == (640, 360)
    assert [s["codec_type"] for s in streams(out)["streams"]] == ["video"]


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_a_portrait_video_stays_upright(tmp_path):
    # A phone held upright writes a landscape picture and a rotation flag
    source = video(tmp_path / "in.mp4", size="1280x720", rotate=90)
    out = tmp_path / "out.mp4"
    await render.transcode_video(source, out, threads=2, timeout_s=120)
    info = await render.probe_video(out)
    assert info.height is not None and info.width is not None
    assert info.height > info.width  # 720 x 1280, turned and no longer flagged


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_an_iphone_mov_in_hevc_is_made_playable(tmp_path):
    try:
        source = video(tmp_path / "in.mov", codec="libx265", container="mov", size="1280x720")
    except subprocess.CalledProcessError:
        pytest.skip("this ffmpeg has no HEVC encoder to make the test clip with")
    out = tmp_path / "out.mp4"
    await render.transcode_video(source, out, threads=2, timeout_s=120)
    assert streams(out)["streams"][0]["codec_name"] == "h264"


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_the_poster_is_a_400_px_webp_from_the_clip(tmp_path):
    source = video(tmp_path / "in.mp4", size="1280x720")
    poster = await render.video_poster(source, tmp_path, 3.0)
    thumb = opened(poster)
    assert thumb.format == "WEBP" and thumb.size == (400, 226)
    short = video(tmp_path / "short.mp4", seconds=1, size="320x240")  # shorter than the 1 s mark
    assert opened(await render.video_poster(short, tmp_path, 1.0)).size == (320, 240)


@needs_ffmpeg
@pytest.mark.req("MED-3")
async def test_a_file_that_is_not_a_video_is_unreadable_before_the_long_step(tmp_path):
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"not really a video" * 50)
    with pytest.raises(render.Unreadable) as e:
        await render.probe_video(junk)
    assert e.value.code in ("unreadable_video", "no_video_stream")
    truncated = video(tmp_path / "ok.mp4")
    cut = tmp_path / "cut.mp4"
    cut.write_bytes(truncated.read_bytes()[:3000])
    with pytest.raises(render.Unreadable):
        await render.transcode_video(cut, tmp_path / "out.mp4", threads=2, timeout_s=60)


@needs_ffmpeg
@pytest.mark.req("MED-2")
async def test_a_video_that_takes_too_long_is_stopped(tmp_path):
    source = video(tmp_path / "in.mp4", seconds=5, size="1920x1080")
    with pytest.raises(render.Unreadable) as e:
        await render.transcode_video(source, tmp_path / "out.mp4", threads=1, timeout_s=0.01)
    assert e.value.code == "video_timeout"
    assert asyncio.get_running_loop().is_running()


async def test_a_host_without_ffmpeg_says_so_rather_than_blaming_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(render.ToolMissing):
        await render.probe_video(tmp_path / "x.mp4")
