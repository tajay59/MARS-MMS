"""The visit board replaces the work record (TRD §3.2.3, BSD `visit_elements`; W11-16, W11-17).

Elements are found by visit and station, newest first, and by organization for the client scope.
What the board replaces goes: each station's embedded work record and phase media, the end's
overrides, the sensor applications, the checklist templates and the units' review flag. Only test
visits existed when this ran (no production data), so they are cleared, not converted. Their
phase files stay in media, staff-only (fail closed, ADR-19).
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    elements = db["visit_elements"]
    await elements.create_index(
        [("visit_id", ASCENDING), ("station_id", ASCENDING), ("created_at", DESCENDING)]
    )
    await elements.create_index("org_id")

    await db["site_visits"].update_many(
        {}, {"$unset": {"stations.$[].work": "", "stations.$[].media": "",
                        "stations.$[].media_override_reason": "", "overrides": ""}},
    )
    names = set(await db.list_collection_names())
    for gone in ("sensor_applications", "checklist_templates"):
        if gone in names:
            await db.drop_collection(gone)

    units = db["sensor_units"]
    await units.update_many({"needs_review": {"$exists": True}}, {"$unset": {"needs_review": ""}})
    try:
        await units.drop_index("needs_review_1")
    except OperationFailure:
        pass  # never made on this database
