"""Making the copy people look at from a photo or a video (PRD MED-1, MED-2, MED-5, MED-7;
TRD §10). Pillow and pillow-heif for photos, ffmpeg and ffprobe for video.

A photo is turned upright, stripped of everything personal (EXIF, GPS, XMP), shrunk to 2048 px on
its longest side and written as WebP, with a 400 px thumbnail. A video becomes an H.264/AAC MP4
that plays in every supported browser, at most 1280 px wide, with a poster frame as its
thumbnail. The functions here take and give paths or bytes; the worker (`jobs/derive.py`) does
the storage and the state changes.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain import derive

try:  # HEIC and HEIF: what an iPhone makes when it is not asked for JPEG
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - declared in pyproject; only a broken install lacks it
    pass

log = logging.getLogger(__name__)

# A photo from a phone is 12 to 50 megapixels; anything past this is a decompression bomb.
Image.MAX_IMAGE_PIXELS = 120_000_000

EXIF_IFD = 0x8769
DATE_TIME_ORIGINAL = 0x9003
OFFSET_TIME_ORIGINAL = 0x9011


class Unreadable(Exception):
    """The file is not a photo or a video the tools can open. `code` goes on the record."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ToolMissing(Exception):
    """ffmpeg or ffprobe is not installed here: a broken host, not a bad file (retry later)."""


@dataclass(frozen=True)
class ImageResult:
    view: bytes
    thumb: bytes
    width: int
    height: int
    captured_at: datetime | None


@dataclass(frozen=True)
class VideoInfo:
    duration_s: float | None
    width: int | None
    height: int | None


# --- Photos --------------------------------------------------------------------------------------


def _captured_at(exif: Image.Exif) -> datetime | None:
    """When the shutter was pressed, as UTC, if the photo says both the time and its offset.
    Without an offset the time is a wall clock in an unknown zone, so it is not guessed: the app
    sends the capture time it read on the phone (TRD §7.5)."""
    try:
        inner = exif.get_ifd(EXIF_IFD)
        text = inner.get(DATE_TIME_ORIGINAL)
        offset = inner.get(OFFSET_TIME_ORIGINAL)
        if not text or not offset:
            return None
        naive = datetime.strptime(str(text).strip(), "%Y:%m:%d %H:%M:%S")  # noqa: DTZ007
        sign = -1 if str(offset).startswith("-") else 1
        hours, _, minutes = str(offset).lstrip("+-").partition(":")
        zone = timezone(sign * timedelta(hours=int(hours), minutes=int(minutes or 0)))
        return naive.replace(tzinfo=zone).astimezone(UTC)
    except (ValueError, TypeError, KeyError, OSError):
        return None


def _webp(image: Image.Image, quality: int, icc: bytes | None) -> bytes:
    out = io.BytesIO()
    # `exif`, `xmp` and the metadata of the source are written only when given, so nothing of the
    # original's EXIF or GPS reaches the copy (MED-7); the colour profile is not personal data.
    image.save(out, "WEBP", quality=quality, method=4, exif=b"", xmp=b"", icc_profile=icc)
    return out.getvalue()


def render_image(path: Path) -> ImageResult:
    try:
        with Image.open(path) as source:
            source.load()
            captured = _captured_at(source.getexif())
            upright = ImageOps.exif_transpose(source)
            icc = source.info.get("icc_profile")
            has_alpha = upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info
            image = upright.convert("RGBA" if has_alpha else "RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            SyntaxError) as e:
        raise Unreadable("unreadable_image") from e
    view = image.copy()
    view.thumbnail((derive.IMAGE_VIEW_PX, derive.IMAGE_VIEW_PX), Image.Resampling.LANCZOS)
    thumb = view.copy()
    thumb.thumbnail((derive.THUMB_PX, derive.THUMB_PX), Image.Resampling.LANCZOS)
    return ImageResult(
        view=_webp(view, derive.IMAGE_QUALITY, icc), thumb=_webp(thumb, derive.THUMB_QUALITY, icc),
        width=view.width, height=view.height, captured_at=captured,
    )


# --- Video ---------------------------------------------------------------------------------------


def tools_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


async def _run(args: list[str], timeout_s: float) -> tuple[int, bytes, bytes]:
    if shutil.which(args[0]) is None:
        raise ToolMissing(args[0])
    process = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise Unreadable("video_timeout") from None
    return process.returncode or 0, out, err


async def probe_video(path: Path, timeout_s: float = 60) -> VideoInfo:
    code, out, err = await _run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         str(path)], timeout_s,
    )
    if code != 0:
        log.warning("ffprobe_failed", extra={"error": err.decode(errors="replace")[-300:]})
        raise Unreadable("unreadable_video")
    try:
        info: dict[str, Any] = json.loads(out)
    except ValueError:
        raise Unreadable("unreadable_video") from None
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise Unreadable("no_video_stream")
    raw = info.get("format", {}).get("duration") or video.get("duration")
    try:
        duration = round(float(raw), 1) if raw is not None else None
    except ValueError:
        duration = None
    return VideoInfo(duration, _int(video.get("width")), _int(video.get("height")))


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def transcode_video(src: Path, dst: Path, *, threads: int, timeout_s: float) -> None:
    """H.264/AAC MP4, at most 1280 px wide (never enlarged), upright, yuv420p so every browser
    plays it, the index first so it starts before it has all arrived (`+faststart`)."""
    code, _, err = await _run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(src),
         "-map", "0:v:0", "-map", "0:a:0?",
         "-vf", f"scale='min({derive.VIDEO_WIDTH},iw)':-2",
         "-c:v", "libx264", "-preset", "medium", "-crf", str(derive.VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
         "-movflags", "+faststart", "-threads", str(threads), str(dst)],
        timeout_s,
    )
    if code != 0:
        log.warning("ffmpeg_failed", extra={"error": err.decode(errors="replace")[-500:]})
        raise Unreadable("unreadable_video")


async def video_poster(src: Path, tmp: Path, duration_s: float | None) -> bytes:
    """A frame at one second (or the start of a shorter clip) as a 400 px WebP."""
    frame = tmp / "poster.jpg"
    at = 1.0 if duration_s is None or duration_s > 1.5 else 0.0
    code, _, err = await _run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", str(at), "-i", str(src),
         "-frames:v", "1", "-vf", f"scale='min({derive.THUMB_PX},iw)':-2", str(frame)], 120,
    )
    if code != 0 or not frame.exists():
        log.warning("poster_failed", extra={"error": err.decode(errors="replace")[-300:]})
        raise Unreadable("unreadable_video")
    try:
        with Image.open(frame) as image:
            return _webp(image.convert("RGB"), derive.THUMB_QUALITY, None)
    except (OSError, ValueError) as e:
        raise Unreadable("unreadable_video") from e
