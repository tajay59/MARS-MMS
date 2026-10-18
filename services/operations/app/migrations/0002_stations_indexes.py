"""Stations module indexes (TRD §5.2, BSD "operations — stations module")."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, GEOSPHERE
from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    stations = db["stations"]
    await stations.create_index("code", unique=True)
    await stations.create_index("qr_token", unique=True)
    await stations.create_index("owner_org_id")
    await stations.create_index("country")
    await stations.create_index([("location", GEOSPHERE)])

    await db["sensor_models"].create_index("key", unique=True)

    units = db["sensor_units"]
    await units.create_index([("model_id", ASCENDING), ("serial", ASCENDING)], unique=True)
    await units.create_index("calibration_due_at")
    await units.create_index("current_org_id")
    await units.create_index([("current_station_id", ASCENDING), ("status", ASCENDING)])

    installations = db["installations"]
    await installations.create_index([("station_id", ASCENDING), ("removed_at", ASCENDING)])
    await installations.create_index([("sensor_unit_id", ASCENDING), ("installed_at", DESCENDING)])
    await installations.create_index("org_id")
    # Visit actions open installations once (TRD §3.2.3); manual ones have no action.
    await installations.create_index(
        "source_action_id", unique=True,
        partialFilterExpression={"source_action_id": {"$type": "string"}},
    )

    calibrations = db["calibrations"]
    await calibrations.create_index([("sensor_unit_id", ASCENDING), ("at", DESCENDING)])
    await calibrations.create_index("station_id")
    await calibrations.create_index("org_id")

    await db["organizations"].create_index("name_key")
