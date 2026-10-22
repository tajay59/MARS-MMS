"""`derive`: the copy of a photo or a video that people look at, and its thumbnail (PRD MED-1,
MED-2, MED-5, MED-7; TRD §10), made after the checks passed and before the file is `ready`.

The original is read from `mms-originals` into a scratch folder, the copy and thumbnail are
written to `mms-media` beside the original's name, and the caller records them in the same
transaction that makes the file `ready`. If anything fails the copies are removed and the file
fails with a code the uploader sees; the original is kept (a photo from a site visit may not be
takeable again).

Video is the heavy part. The worker runs **one video at a time** and gives ffmpeg a few threads,
so a two-minute clip cannot starve the other services on a shared host (R7, R8).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain import derive
from app.domain.media import Kind
from app.repo import render
from app.repo.storage import StorageError
from app.services import Services

log = logging.getLogger(__name__)

# Shared by every file this process handles: videos queue up behind one another
_video_slot = asyncio.Semaphore(1)


@dataclass(frozen=True)
class Derived:
    """What the record gets when the file becomes `ready`."""

    fields: dict[str, Any]
    keys: tuple[str, ...]  # what was written, to remove if the transaction does not happen


async def make(svc: Services, doc: dict[str, Any]) -> Derived:
    """Raises `render.Unreadable` for a file the tools cannot open, `render.ToolMissing` when the
    host lacks ffmpeg, `StorageError` when the store fails (the caller retries those two)."""
    kind = Kind(doc["kind"])
    view_key, thumb_key = derive.derived_keys(doc["original_key"], kind)
    bucket_in, bucket_out = svc.bucket(doc["kind"]), svc.settings.bucket_media
    scratch = svc.settings.work_dir or None
    with tempfile.TemporaryDirectory(prefix="mms-media-", dir=scratch) as folder:
        tmp = Path(folder)
        source = tmp / "original"
        await svc.storage.download_to(bucket_in, doc["original_key"], source)
        if kind is Kind.IMAGE:
            return await _image(svc, source, bucket_out, view_key, thumb_key)
        async with _video_slot:
            return await _video(svc, source, tmp, bucket_out, view_key, thumb_key)


async def _image(
    svc: Services, source: Path, bucket: str, view_key: str, thumb_key: str
) -> Derived:
    result = await asyncio.to_thread(render.render_image, source)
    written: list[str] = []
    try:
        await svc.storage.put(bucket, view_key, result.view, derive.view_type("image"))
        written.append(view_key)
        await svc.storage.put(bucket, thumb_key, result.thumb, "image/webp")
        written.append(thumb_key)
    except StorageError:
        await remove(svc, tuple(written))
        raise
    fields = derive.derived_fields(
        view_key, thumb_key, width=result.width, height=result.height, duration_s=None,
        captured_at=result.captured_at, view_bytes=len(result.view),
    )
    return Derived(fields, (view_key, thumb_key))


async def _video(
    svc: Services, source: Path, tmp: Path, bucket: str, view_key: str, thumb_key: str
) -> Derived:
    settings = svc.settings
    await render.probe_video(source)  # refuses a file with no video in it before the long step
    out = tmp / "view.mp4"
    await render.transcode_video(
        source, out, threads=settings.video_threads, timeout_s=settings.video_timeout_s
    )
    info = await render.probe_video(out)
    poster = await render.video_poster(out, tmp, info.duration_s)
    written: list[str] = []
    try:
        size = await svc.storage.upload_file(bucket, view_key, out, derive.view_type("video"))
        written.append(view_key)
        await svc.storage.put(bucket, thumb_key, poster, "image/webp")
        written.append(thumb_key)
    except StorageError:
        await remove(svc, tuple(written))
        raise
    captured: datetime | None = None
    fields = derive.derived_fields(
        view_key, thumb_key, width=info.width, height=info.height, duration_s=info.duration_s,
        captured_at=captured, view_bytes=size,
    )
    return Derived(fields, (view_key, thumb_key))


async def remove(svc: Services, keys: tuple[str, ...]) -> None:
    """Best effort: a copy left behind is harmless (nothing points at it) and the key is never
    reused."""
    for key in keys:
        try:
            await svc.storage.delete(svc.settings.bucket_media, key)
        except StorageError:
            log.warning("derived_cleanup_failed", extra={"key": key})
