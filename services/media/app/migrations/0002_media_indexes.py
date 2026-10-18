"""The media collection's indexes (TRD §5.3, BSD "media")."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    media = db["media"]
    await media.create_index("owner_ref")
    await media.create_index([("org_id", ASCENDING), ("kind", ASCENDING)])
    await media.create_index([("status", ASCENDING), ("updated_at", ASCENDING)])
    await media.create_index("upload_id", sparse=True)
    # "Is this the file I was uploading before the reload?" (create_upload's resume lookup)
    await media.create_index([
        ("uploaded_by", ASCENDING), ("owner_ref", ASCENDING),
        ("checksum_sha256", ASCENDING), ("size_bytes", ASCENDING), ("status", ASCENDING),
    ])
