"""A station's ID in the system its data was imported from is unique where set (W5-8)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["stations"].create_index(
        "external_id", unique=True, partialFilterExpression={"external_id": {"$type": "string"}}
    )
