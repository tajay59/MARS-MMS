"""Internal-network routes. Nginx never routes `/internal/` (TRD §2.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from mms_common.auth import ServicePrincipal, require_service
from mms_common.ids import UUID7_PATTERN
from mms_common.snapshot import SnapshotPage, page

from app.api.context import CtxDep
from app.events.publish import calibration_data, station_data, unit_data

router = APIRouter(tags=["internal"])

SnapshotReader = Annotated[ServicePrincipal, Depends(require_service("report", "platform"))]


@router.get("/internal/snapshot/{entity}")
async def snapshot(
    svc: SnapshotReader,
    ctx: CtxDep,
    entity: Annotated[str, Path(pattern="^(stations|sensor_units|calibrations)$")],
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> SnapshotPage:
    """Current state for read-model backfill (TRD §8.6), shaped like the events' data.
    Requests and visits join in Phases 3 and 4."""
    result = await page(ctx.db[entity], after=after, limit=limit)
    if entity == "stations":
        items = [{**station_data(d), "aggregate_version": d["version"]} for d in result.items]
    elif entity == "sensor_units":
        items = [{**unit_data(d), "aggregate_version": d["version"]} for d in result.items]
    else:
        items = [
            {**calibration_data(d, None), "aggregate_version": d["version"]}
            for d in result.items
        ]
    return SnapshotPage(items=items, next_after=result.next_after)
