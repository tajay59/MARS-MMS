"""The field bundle route (TRD §3.2.1; PRD OFF-1; AFD J5 step 4; W13-9).

`GET /api/v1/visits/{id}/field-bundle` returns what a phone needs to carry out the visit with no
signal and records, in the same transaction as its event, that the visit is prepared on that
phone (`prepared_on`). It reads through the routes' own functions, so a staff-only field stays
staff only and the bundle can never show more than the pages do (rules 3 and 6).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from mms_common.auth import User, require_roles
from mms_common.ids import UUID7_PATTERN
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx, CtxDep
from app.api.requests import request_routes
from app.api.stations import document_routes, views
from app.api.stations.doc_schemas import ConfigVersionOut
from app.api.stations.schemas import CalibrationOut, StationDetail
from app.api.visits import element_routes, visit_routes
from app.api.visits.bundle_schemas import BundleFile, BundleStation, FieldBundle
from app.domain.visits import bundle as rules
from app.events.publish import ev
from app.repo.requests import requests as request_repo
from app.repo.stations import documents as document_repo
from app.repo.stations import history
from app.repo.stations import stations as station_repo
from app.repo.visits import visits as repo

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])

Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
DeviceId = Annotated[str, Query(pattern=UUID7_PATTERN)]

CALIBRATIONS_PER_STATION = 50


def _files(stations: list[BundleStation]) -> list[BundleFile]:
    """Configuration files first (required), then documents, each file once."""
    files: dict[str, BundleFile] = {}
    for item in stations:
        sid = item.station.id
        if item.config_version is not None:
            for f in item.config_version.files:
                files.setdefault(f.media_id, BundleFile(
                    kind="config", media_id=f.media_id, document_id=None, station_id=sid,
                    name=f.filename, size=f.size_bytes, sha256=f.sha256, required=True,
                ))
    for item in stations:
        sid = item.station.id
        documents = [
            *item.documents.station, *(d for m in item.documents.models for d in m.documents)
        ]
        for d in documents:
            if d.media_id and d.status == "available":
                files.setdefault(d.media_id, BundleFile(
                    kind="document", media_id=d.media_id, document_id=d.id, station_id=sid,
                    name=d.filename, size=d.size_bytes, sha256=None, required=False,
                ))
    return list(files.values())


async def _station(ctx: Ctx, visit: dict[str, Any], station_id: str, user: User) -> BundleStation:
    doc = await station_repo.require(ctx.db, station_id, user)
    installed = await views.installed_units(ctx, station_id, user)
    due = min((u.calibration_due_at for u in installed if u.calibration_due_at), default=None)
    calibrations = await history.search_calibrations(
        ctx.db, unit_id=None, station_id=station_id, after=None, limit=CALIBRATIONS_PER_STATION
    )
    versions = await document_repo.list_versions(ctx.db, station_id)  # newest first
    board = await element_routes.list_elements(visit["_id"], station_id, user, ctx)
    return BundleStation(
        station=StationDetail.build(doc, user, installed, due),
        calibrations=[CalibrationOut.of(c) for c in calibrations],
        config_version=ConfigVersionOut.of(versions[0]) if versions else None,
        documents=await document_routes.station_documents(station_id, user, ctx),
        board=board.items, can_add=board.can_add,
    )


@router.get("/{id}/field-bundle")
async def field_bundle(
    id: IdPath, device_id: DeviceId, user: Worker, ctx: CtxDep
) -> FieldBundle:
    """OFF-1: the request, the visit's stations with their sensors, calibration status, latest
    configuration version, documents and boards. Everyone attending (and an admin) may prepare a
    planned or started visit; asking again from the same phone refreshes the record of it."""
    visit = await repo.require(ctx.db, id, user)
    rules.check_attending(user.id, user.is_admin, visit)
    rules.check_preparable(visit)
    request = await request_repo.require(ctx.db, visit["request_id"])
    stations = [await _station(ctx, visit, s["station_id"], user) for s in visit["stations"]]
    now = ctx.clock.now()
    entry = rules.prepared_entry(user_id=user.id, user_name=user.name, device_id=device_id, at=now)
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        # Read again inside the transaction: the visit may have been cancelled meanwhile
        current = await repo.require(ctx.db, id, user, s)
        rules.check_preparable(current)
        updated = await repo.set_prepared_on(
            ctx.db, id, rules.merge_prepared(current.get("prepared_on", []), entry), s
        )
        await emitter.visit(
            ev.VisitPrepared, "visit.prepared", updated, request, s,
            user_id=user.id, device_id=device_id,
        )
        holder["visit"] = updated

    await ctx.tx(save)
    return FieldBundle(
        bundle_version=rules.BUNDLE_VERSION, prepared_at=now,
        visit=await visit_routes.built(ctx, holder["visit"], request, user),
        request=await request_routes._detail(ctx, request, user),  # noqa: SLF001
        stations=stations, files=_files(stations),
    )
