"""Payloads of the events the media service produces on `mms.media.events` (TRD §8.4).

Message key: `media_id` (TRD §8.1). `aggregate_version` is the media record's `version`.
The documents path (Phase 2) emits `uploaded`, `processed`, `failed` and `deleted`; images and
video (Phase 4) reuse them.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mms_common.events.registry import register


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaData(_Data):
    media_id: str
    owner_ref: str
    kind: str
    filename: str
    size_bytes: int


@register("media.uploaded")
class MediaUploaded(MediaData):
    """The last part is in and the object is whole; scanning and checks follow."""

    uploaded_by: str


@register("media.processed")
class MediaProcessed(MediaData):
    """The file passed its checks and is ready. `scan_status` is `clean`, or `skipped` where
    the scanner is switched off (staging); production never starts with it off."""

    scan_status: str
    checksum_sha256: str
    # Photos and video (W11): the size of the copy people look at and, for a video, how long it
    # runs. Optional, so version 1 still holds for documents
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    captured_at: datetime | None = None


@register("media.failed")
class MediaFailed(MediaData):
    """`reason` is a code: `checksum_mismatch`, `bad_type`, `infected`, `size_mismatch`,
    `stale`, `scan_failed`."""

    reason: str


@register("media.deleted")
class MediaDeleted(MediaData):
    pass
