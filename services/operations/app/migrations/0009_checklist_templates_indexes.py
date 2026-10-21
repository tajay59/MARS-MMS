"""Indexes for checklist templates (TRD §5.4): a family's versions, and one active current template
per scope (a station type, or a sensor model's add-on)."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    templates = db["checklist_templates"]
    await templates.create_index([("family_id", ASCENDING), ("version", ASCENDING)], unique=True)
    await templates.create_index(
        "scope_key", unique=True,
        partialFilterExpression={"is_current": True, "active": True},
    )
    await templates.create_index([("is_current", ASCENDING), ("name", ASCENDING)])
