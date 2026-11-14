"""Indexes for client reports (TRD §5.2): a request's reports, the station history's reports
(CRP-5) and the organization's, and the one-file-one-owner lookups."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    reports = db["client_reports"]
    await reports.create_index([("request_id", ASCENDING), ("_id", DESCENDING)])
    await reports.create_index([("org_id", ASCENDING), ("status", ASCENDING)])
    await reports.create_index("station_ids")
    await reports.create_index("file.media_id", sparse=True)
    await reports.create_index("form.images.media_id", sparse=True)
