"""Indexes for comments (TRD §5.4): a request's thread, oldest first, and the one file one
comment rule."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    comments = db["comments"]
    await comments.create_index([("request_id", ASCENDING), ("_id", ASCENDING)])
    await comments.create_index("attachments.media_id", sparse=True)
    await db["requests"].create_index("attachments.media_id", sparse=True)
