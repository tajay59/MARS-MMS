"""Indexes for documents, configuration versions and media verdicts (TRD §5.2)."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    documents = db["documents"]
    # One file belongs to one document: a retry or a second form cannot attach it twice.
    await documents.create_index("media_id", unique=True)
    await documents.create_index([("scope", ASCENDING), ("scope_id", ASCENDING),
                                  ("is_current", ASCENDING)])
    await documents.create_index("org_id")

    versions = db["config_versions"]
    await versions.create_index([("station_id", ASCENDING), ("version", ASCENDING)], unique=True)
    # CFG-2: a file is part of one version, and versions are never rewritten.
    await versions.create_index("files.media_id", unique=True)
