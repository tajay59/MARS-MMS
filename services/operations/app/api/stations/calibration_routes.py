"""Calibrations (TRD §3.2; PRD CAL-1, CAL-3, CAL-4, CAL-6). Staff only."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from mms_common.auth import User, require_roles, require_staff
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import CtxDep
from app.api.stations.document_routes import file_facts
from app.api.stations.schemas import (
    CalibrationIn,
    CalibrationOut,
    CalibrationPage,
    DueList,
    DueStation,
    DueUnit,
    ModelSummary,
)
from app.domain.stations import documents
from app.domain.stations import sensors as rules
from app.repo.stations import history, models, stations, units
from app.repo.stations.common import stamp

router = APIRouter(prefix="/api/v1/calibrations", tags=["calibrations"])

Staff = Annotated[User, Depends(require_staff())]
Writer = Annotated[User, Depends(require_roles("technician", "admin"))]


@router.get("/due")
async def calibration_due(
    staff: Staff,
    ctx: CtxDep,
    within_days: Annotated[int, Query(ge=0, le=365)] = rules.DUE_SOON_DAYS,
    org_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    country: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
    station_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 1000,
) -> DueList:
    """CAL-4: units overdue or due within `within_days`, overdue first."""
    now = ctx.clock.now()
    station_ids: list[str] | None = None
    if country or station_id:
        station_ids = await stations.ids_where(ctx.db, country=country, station_id=station_id)
    found = await units.due(ctx.db, until=now + timedelta(days=within_days), org_id=org_id,
                            station_ids=station_ids, limit=limit)
    model_docs = await models.by_ids(ctx.db, [u["model_id"] for u in found])
    station_docs = await stations.by_ids(
        ctx.db, [u["current_station_id"] for u in found if u.get("current_station_id")]
    )
    items: list[DueUnit] = []
    for unit in found:
        station = station_docs.get(unit.get("current_station_id") or "")
        state = rules.due_state(unit["calibration_due_at"], now, within_days)
        items.append(DueUnit(
            unit_id=unit["_id"], serial=unit["serial"], status=unit["status"],
            model=ModelSummary.of(model_docs.get(unit["model_id"]), unit["model_id"]),
            station=DueStation(
                id=station["_id"], code=station["code"], name=station["name"],
                country=station["country"], owner_org_id=station["owner_org_id"],
                owner_org_name=station.get("owner_org_name"),
            ) if station else None,
            parameter=unit.get("current_parameter"),
            last_calibrated_at=unit.get("last_calibrated_at"),
            calibration_due_at=unit["calibration_due_at"],
            due_state=(state or rules.DueState.DUE_SOON).value,
        ))
    return DueList(items=items, within_days=within_days)


@router.get("")
async def list_calibrations(
    staff: Staff,
    ctx: CtxDep,
    sensor_unit_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    station_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> CalibrationPage:
    """Newest first. `station_id` lists what was calibrated while at that station."""
    found = await history.search_calibrations(
        ctx.db, unit_id=sensor_unit_id, station_id=station_id, after=after, limit=limit + 1
    )
    more = len(found) > limit
    found = found[:limit]
    return CalibrationPage(items=[CalibrationOut.of(d) for d in found],
                           next_after=found[-1]["_id"] if more else None)


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_calibration(body: CalibrationIn, user: Writer, ctx: CtxDep) -> CalibrationOut:
    """CAL-1. The unit's last calibration and due date follow the newest record (CAL-3); a
    failed one flags the unit for follow-up (CAL-6). A certificate is a PDF the person already
    uploaded for this unit (`calibration:<unit id>`) that has passed media's checks."""
    unit = await units.require(ctx.db, body.sensor_unit_id)
    model = await models.get(ctx.db, unit["model_id"])
    now = ctx.clock.now()
    rules.check_when(body.at, now)
    readings = [r.model_dump() for r in body.readings]
    rules.check_readings(readings)
    certificate: str | None = None
    if body.certificate_media_id:
        facts = await file_facts(ctx, body.certificate_media_id)
        documents.check_file(
            facts, owner=documents.certificate_owner_ref(unit["_id"]),
            kinds=documents.CERTIFICATE_KINDS, user_id=user.id, ready_only=True,
            field="certificate_media_id",
        )
        certificate = body.certificate_media_id
    station_id = unit.get("current_station_id")
    doc = stamp({
        "_id": new_id(), "sensor_unit_id": unit["_id"], "station_id": station_id,
        "org_id": unit.get("current_org_id"), "visit_id": None, "at": body.at,
        "method": body.method,
        "reference_instrument": body.reference_instrument.model_dump(mode="json")
        if body.reference_instrument else None,
        "readings": readings, "result": body.result, "certificate_media_id": certificate,
        "performed_by": body.performed_by or user.name, "notes": body.notes,
    }, now, user.id)
    changes = rules.unit_after_calibration(unit, model, body.at, body.result)
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        updated = unit
        if changes:
            updated = await units.update(
                ctx.db, unit["_id"], changes, now=now, by=user.id,
                expected_version=unit["version"], session=s,
            )
        await history.insert_calibration(ctx.db, doc, s)
        await emitter.calibration(doc, updated, s)

    await ctx.tx(save)
    return CalibrationOut.of(doc)
