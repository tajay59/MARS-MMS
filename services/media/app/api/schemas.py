"""Request and response bodies (extra fields are refused)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field

SHA256_PATTERN = "^[0-9a-f]{64}$"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadIn(_In):
    media_id: str = Field(pattern=UUID7_PATTERN, description="Made on the device (rule 9)")
    owner_ref: str = Field(min_length=3, max_length=200)
    kind: str = Field(min_length=2, max_length=16)
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=1, le=2**40)
    sha256: str = Field(pattern=SHA256_PATTERN, description="Lowercase hex, 64 characters")


class CaptionIn(_In):
    caption: str | None = Field(default=None, max_length=500)


class UrlIn(_In):
    inline: bool = True


class MediaOut(BaseModel):
    id: str
    owner_ref: str
    kind: str
    filename: str
    size_bytes: int
    status: str
    visibility: str
    caption: str | None = None
    scan_status: str | None = None
    checksum_sha256: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, doc: dict[str, Any]) -> MediaOut:
        return cls(
            id=doc["_id"], owner_ref=doc["owner_ref"], kind=doc["kind"], filename=doc["filename"],
            size_bytes=doc["size_bytes"], status=doc["status"], visibility=doc["visibility"],
            caption=doc.get("caption"), scan_status=doc.get("scan_status"),
            checksum_sha256=doc.get("checksum_sha256"), error=doc.get("error"),
            created_at=doc["created_at"], updated_at=doc["updated_at"],
        )


class PartUrl(BaseModel):
    part_number: int
    url: str


class UploadOut(BaseModel):
    """Where an upload stands. `parts_done` is what the store holds; `urls` are for the parts
    still missing and last until `expires_at` (ask `/parts` again after that)."""

    media_id: str
    status: str
    part_size: int
    part_count: int
    parts_done: list[int]
    urls: list[PartUrl]
    expires_at: datetime | None
    resumed: bool
    media: MediaOut


class MediaDetail(MediaOut):
    urls: dict[str, str] = Field(default_factory=dict, description="view and download, 10 minutes")


class MediaPage(BaseModel):
    items: list[MediaOut]
    next_after: str | None = None


class UrlOut(BaseModel):
    url: str
    expires_at: datetime


class MediaInfo(BaseModel):
    """What operations checks before it attaches a file to a document."""

    id: str
    owner_ref: str
    kind: str
    filename: str
    size_bytes: int
    status: str
    uploaded_by: str
    org_id: str | None
    checksum_sha256: str
    scan_status: str | None = None
