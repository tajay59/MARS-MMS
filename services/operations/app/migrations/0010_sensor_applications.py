"""Sensor actions of a visit (TRD §3.2.3, BSD `sensor_applications`): what each action did to the
inventory, found by visit and station, and units found by serial alone (a serial is unique only
within its model) or flagged for review (SEN-5)."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["sensor_applications"].create_index(
        [("visit_id", ASCENDING), ("station_id", ASCENDING), ("seq", ASCENDING)]
    )
    units = db["sensor_units"]
    await units.create_index("serial")
    await units.create_index("needs_review", partialFilterExpression={"needs_review": True})
