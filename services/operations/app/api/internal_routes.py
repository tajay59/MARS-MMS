"""Internal-network routes. Nginx never routes `/internal/` (TRD §2.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from mms_common.auth import ServicePrincipal, require_service
from mms_common.errors import Forbidden, NotFound
from mms_common.ids import UUID7_PATTERN
from mms_common.snapshot import SnapshotPage, page
from pydantic import BaseModel, Field

from app.api.context import CtxDep
from app.api.stations.calibration_routes import due_list
from app.api.stations.schemas import DueList
from app.domain.visits import media as visit_rules
from app.events.publish import (
    calibration_data,
    request_data,
    station_data,
    unit_data,
    visit_snapshot,
)
from app.repo.requests import requests as request_repo
from app.repo.stations import models, units
from app.repo.stations import stations as station_repo
from app.repo.visits import visits as visit_repo

router = APIRouter(tags=["internal"])

SnapshotReader = Annotated[ServicePrincipal, Depends(require_service("report", "platform"))]
MediaService = Annotated[ServicePrincipal, Depends(require_service("media"))]
ReportService = Annotated[ServicePrincipal, Depends(require_service("report"))]
PlatformService = Annotated[ServicePrincipal, Depends(require_service("platform"))]
WRITE_ROLES = frozenset({"technician", "admin"})


class AttachableOut(BaseModel):
    org_id: str | None  # the organization a file for this owner belongs to; None for models


class LabelsIn(BaseModel):
    station_ids: list[Annotated[str, Field(pattern=UUID7_PATTERN)]] = Field(
        min_length=1, max_length=200
    )


class LabelOut(BaseModel):
    station_id: str
    code: str
    name: str
    qr_token: str
    org_name: str
    country: str


@router.get("/internal/calibrations/due")
async def calibrations_due(
    svc: PlatformService, ctx: CtxDep,
    within_days: Annotated[int, Query(ge=0, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=2000)] = 1000,
) -> DueList:
    """The weekly digest's list (CAL-5): the same units as the staff list, for every
    organization, read by platform with its service token (rule 1)."""
    return await due_list(ctx, within_days=within_days, limit=limit)


@router.post("/internal/labels")
async def labels(body: LabelsIn, svc: ReportService, ctx: CtxDep) -> list[LabelOut]:
    """What a label sheet prints (QR-6): the code, name and QR token of each station, in the
    order asked. Stations that do not exist are left out. Tokens never travel in events or
    snapshots, so this is the only place report can read them."""
    found = await station_repo.by_ids(ctx.db, body.station_ids)
    return [
        LabelOut(
            station_id=d["_id"], code=d["code"], name=d["name"], qr_token=d["qr_token"],
            org_name=d["owner_org_name"], country=d["country"],
        )
        for sid in dict.fromkeys(body.station_ids)
        if (d := found.get(sid)) is not None
    ]


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
    elif parts[0] == "request" and len(parts) == 2:
        # The request may not exist yet: its files are uploaded while the form is still open
        # (W9-8). Only people who can make a request attach to one that is not there.
        found = await request_repo.get(ctx.db, parts[1])
        if found is None:
            if not held & {"client", "admin"}:
                raise Forbidden()
            return AttachableOut(org_id=org_id or None)
        if "client" in held and found["org_id"] != (org_id or None):
            raise NotFound()
        if not held & {"client", "technician", "admin"}:
            raise Forbidden()
        return AttachableOut(org_id=found["org_id"])
    elif parts[0] == "visit" and (target := visit_rules.parse_owner_ref(owner_ref)) is not None:
        # A photo or video for a station of a visit: staff attending it (W11-10). A client has
        # no way to add one, and a visit they cannot see does not exist for them.
        found_visit = await visit_repo.get(ctx.db, target[0])
        if found_visit is None or "client" in held:
            raise NotFound()
        if target[1] not in {s["station_id"] for s in found_visit["stations"]}:
            raise NotFound()
        if not held & WRITE_ROLES:
            raise Forbidden()
        if "admin" not in held and user_id not in found_visit["staff_ids"]:
            raise Forbidden()
        return AttachableOut(org_id=found_visit["org_id"])
    elif parts[0] == "comment" and len(parts) == 3:
        # A comment's files go with the comment, so the request must exist and be the caller's
        found = await request_repo.get(ctx.db, parts[1])
        if found is None or ("client" in held and found["org_id"] != (org_id or None)):
            raise NotFound()
        if not held & {"client", "technician", "admin"}:
            raise Forbidden()
        return AttachableOut(org_id=found["org_id"])
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
    entity: Annotated[str, Path(pattern="^(stations|sensor_units|calibrations|requests|visits)$")],
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> SnapshotPage:
    """Current state for read-model backfill (TRD §8.6), shaped like the events' data.
    Visits are in `site_visits`."""
    result = await page(ctx.db["site_visits" if entity == "visits" else entity], after=after,
                        limit=limit)
    if entity == "stations":
        items = [{**station_data(d), "aggregate_version": d["version"]} for d in result.items]
    elif entity == "sensor_units":
        items = [{**unit_data(d), "aggregate_version": d["version"]} for d in result.items]
    elif entity == "requests":
        items = [{**request_data(d), "aggregate_version": d["version"]} for d in result.items]
    elif entity == "visits":
        items = [{**visit_snapshot(d), "aggregate_version": d["version"]} for d in result.items]
    else:
        items = [
            {**calibration_data(d, None), "aggregate_version": d["version"]}
            for d in result.items
        ]
    return SnapshotPage(items=items, next_after=result.next_after)
