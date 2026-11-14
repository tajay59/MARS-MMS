"""What is made from a photo or a video, and where it is kept (PRD MED-1, MED-2, MED-7; TRD §10).
No I/O.

The original stays in `mms-originals` for 30 days after the copy is ready, then is purged. The
copy people look at, and its thumbnail, are made by the worker and live in `mms-media` beside
the original's name, so nothing is ever overwritten.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.domain.media import Kind

IMAGE_VIEW_PX = 2048  # the longest side of the copy people look at
THUMB_PX = 400
IMAGE_QUALITY = 80
THUMB_QUALITY = 75
VIDEO_WIDTH = 1280  # at most; smaller videos are not enlarged
VIDEO_CRF = 28
KEEP_ORIGINALS = timedelta(days=30)


def derived_keys(original_key: str, kind: Kind) -> tuple[str, str]:
    """`(view key, thumbnail key)` beside the original: `.../<media id>/original.jpg` gives
    `.../<media id>/view.webp` and `.../<media id>/thumb.webp`. Keys are made by the backend and
    never reused (TRD §10.1)."""
    folder = original_key.rsplit("/", 1)[0]
    view = "view.mp4" if kind is Kind.VIDEO else "view.webp"
    return f"{folder}/{view}", f"{folder}/thumb.webp"


def view_type(kind: str) -> str:
    return "video/mp4" if kind == Kind.VIDEO.value else "image/webp"


def purge_cutoff(now: datetime) -> datetime:
    """Originals that became ready before this are purged."""
    return now - KEEP_ORIGINALS


def derived_fields(
    view_key: str, thumb_key: str, *, width: int | None, height: int | None,
    duration_s: float | None, captured_at: datetime | None, view_bytes: int,
) -> dict[str, Any]:
    return {
        "processed_key": view_key, "thumbnail_key": thumb_key, "width": width, "height": height,
        "duration_s": duration_s, "captured_at": captured_at, "processed_size_bytes": view_bytes,
    }
