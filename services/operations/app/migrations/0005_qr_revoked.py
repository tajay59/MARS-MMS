"""Revoked QR tokens are found by token (the `_id`); this lists a station's history (QR-7)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["qr_revoked"].create_index("station_id")
