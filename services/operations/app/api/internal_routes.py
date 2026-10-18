"""Internal-network routes. Nginx never routes `/internal/` (TRD §2.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from mms_common.auth import ServicePrincipal, require_service
from mms_common.errors import Forbidden, NotFound
from mms_common.ids import UUID7_PATTERN
from mms_common.snapshot import SnapshotPage, page
from pydantic import BaseModel

from app.api.context import CtxDep
from app.events.publish import calibration_data, station_data, unit_data
from app.repo.stations import models, units
from app.repo.stations import stations as station_repo

router = APIRouter(tags=["internal"])

SnapshotReader = Annotated[ServicePrincipal, Depends(require_service("report", "platform"))]
MediaService = Annotated[ServicePrincipal, Depends(require_service("media"))]
WRITE_ROLES = frozenset({"technician", "admin"})


class AttachableOut(BaseModel):
    org_id: str | None  # the organization a file for this owner belongs to; None for models


@router.get("/internal/attachable")
async def attachable(
    svc: MediaService,
    ctx: CtxDep,
    owner_ref: Annotated[str, Query(min_length=3, max_length=200)],
    user_id: Annotated[str, Query(max_length=64)],
    roles: Annotated[str, Query(max_length=100)] = "",
    org_id: Annotated[str, Query(max_length=64)] = "",
) -> AttachableOut:
    """The owner check on upload (TRD §3.3): may this user attach a file to this owner, and
    which organization does the file then belong to? Not found for an owner that does not
    exist or that a client cannot see (rule 4); forbidden for a role that may not write."""
    held = {r for r in roles.split(",") if r}
    parts = owner_ref.split(":")
    owner_org: str | None
    if parts[:2] in (["document", "station"],) and len(parts) == 3:
        station = await station_repo.get(ctx.db, parts[2])
        if station is None:
            raise NotFound()
        owner_org = station["owner_org_id"]
    elif parts[0] == "config" and len(parts) == 2:
        station = await station_repo.get(ctx.db, parts[1])
        if station is None:
            raise NotFound()
        owner_org = station["owner_org_id"]
    elif parts[:2] == ["document", "model"] and len(parts) == 3:
        if "client" in held or await models.get(ctx.db, parts[2]) is None:
            raise NotFound()  # the catalogue is staff-only
        owner_org = None
    elif parts[0] == "calibration" and len(parts) == 2:
        unit = await units.get(ctx.db, parts[1])
        if unit is None or "client" in held:
            raise NotFound()
        owner_org = unit.get("current_org_id")
    else:
        raise NotFound()
    if "client" in held and owner_org != (org_id or None):
        raise NotFound()  # another organization's station
    if not held & WRITE_ROLES:
        raise Forbidden()  # a viewer, or a client on a staff-only owner
    return AttachableOut(org_id=owner_org)


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
