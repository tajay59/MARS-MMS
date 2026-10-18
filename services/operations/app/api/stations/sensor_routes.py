"""Sensor models and units (TRD §3.2; PRD SEN-1 to SEN-3, CAL-3). Staff only: clients see
units through their stations (STN-4)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from mms_common.auth import User, require_roles, require_staff
from mms_common.errors import Conflict, VersionConflict
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import CtxDep
from app.api.stations import views
from app.api.stations.schemas import (
    EditableUnitStatus,
    InstallIn,
    Kind,
    RemoveIn,
    SensorModelIn,
    SensorModelList,
    SensorModelOut,
    SensorModelPatch,
    SensorUnitDetail,
    SensorUnitIn,
    SensorUnitOut,
    SensorUnitPage,
    SensorUnitPatch,
    UnitStatus,
)
from app.domain.stations import sensors as rules
from app.domain.stations import stations as station_rules
from app.events.publish import ev
from app.repo.stations import history, models, stations, units
from app.repo.stations.common import stamp

model_router = APIRouter(prefix="/api/v1/sensor-models", tags=["sensor-models"])
unit_router = APIRouter(prefix="/api/v1/sensor-units", tags=["sensor-units"])

Staff = Annotated[User, Depends(require_staff())]
Writer = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


class ModelTaken(Conflict):
    code, title = "model_taken", "This manufacturer and model are already in the catalogue"


class SerialTaken(Conflict):
    code, title = "serial_taken", "A unit of this model with this serial already exists"


# --- Sensor models (SEN-1) -------------------------------------------------------------------


@model_router.get("")
async def list_models(
    staff: Staff,
    ctx: CtxDep,
    kind: Annotated[Kind | None, Query()] = None,
    parameter: Annotated[str | None, Query(max_length=station_rules.PARAMETER_MAX_LENGTH)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> SensorModelList:
    found = await models.search(
        ctx.db, kind=kind, parameter=parameter.upper() if parameter else None, q=q
    )
    return SensorModelList(items=[SensorModelOut.of(d) for d in found])


@model_router.post("", status_code=status.HTTP_201_CREATED)
async def create_model(body: SensorModelIn, user: Writer, ctx: CtxDep) -> SensorModelOut:
    doc = stamp({
        "_id": new_id(), "key": rules.model_key(body.manufacturer, body.model),
        "kind": body.kind, "manufacturer": body.manufacturer, "model": body.model,
        "parameters": station_rules.check_parameters(body.parameters),
        "default_calibration_interval_days": body.default_calibration_interval_days,
    }, ctx.clock.now(), user.id)
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        await models.insert(ctx.db, doc, s)
        await emitter.sensor_model(ev.SensorModelCreated, doc, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise ModelTaken() from exc
    return SensorModelOut.of(doc)


@model_router.get("/{id}")
async def get_model(id: IdPath, staff: Staff, ctx: CtxDep) -> SensorModelOut:
    return SensorModelOut.of(await models.require(ctx.db, id))


@model_router.patch("/{id}")
async def patch_model(
    id: IdPath, body: SensorModelPatch, user: Writer, ctx: CtxDep
) -> SensorModelOut:
    """A new default interval moves the due date of every unit that follows it (CAL-3)."""
    current = await models.require(ctx.db, id)
    wanted: dict[str, Any] = {
        f: getattr(body, f) for f in body.model_fields_set - {"version"}
    }
    if "parameters" in wanted:
        wanted["parameters"] = station_rules.check_parameters(wanted["parameters"] or [])
    for field in ("kind", "manufacturer", "model"):
        if field in wanted and wanted[field] is None:
            del wanted[field]
    changes = station_rules.changed_fields(current, wanted)
    if "manufacturer" in changes or "model" in changes:
        changes["key"] = rules.model_key(
            changes.get("manufacturer", current["manufacturer"]),
            changes.get("model", current["model"]),
        )
    if not changes:
        if body.version != current["version"]:
            raise VersionConflict()
        return SensorModelOut.of(current)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await models.update(
            ctx.db, id, changes, now=now, by=user.id, expected_version=body.version, session=s
        )
        await emitter.sensor_model(ev.SensorModelUpdated, updated, s, before=current,
                                   changed_fields=sorted(changes.keys() - {"key"}))
        if "default_calibration_interval_days" in changes:
            for unit in await units.using_default_interval(ctx.db, id, s):
                due = rules.due_at(unit.get("last_calibrated_at"),
                                   rules.interval_days(unit, updated))
                if due == unit.get("calibration_due_at"):
                    continue
                moved = await units.update(
                    ctx.db, unit["_id"], {"calibration_due_at": due}, now=now, by=user.id,
                    expected_version=None, session=s,
                )
                await emitter.unit(ev.SensorUnitUpdated, moved, s, before=unit,
                                   changed_fields=["calibration_due_at"])
        return updated

    try:
        updated = await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise ModelTaken() from exc
    return SensorModelOut.of(updated)


# --- Sensor units (SEN-2, SEN-3) -------------------------------------------------------------


@unit_router.get("")
async def list_units(
    staff: Staff,
    ctx: CtxDep,
    status_: Annotated[UnitStatus | None, Query(alias="status")] = None,
    model_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    station_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    needs_review: bool | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SensorUnitPage:
    filters = units.Filters(status=status_, model_id=model_id, station_id=station_id,
                            needs_review=needs_review, q=q)
    found = await units.search(ctx.db, staff, filters, after=after, limit=limit + 1)
    more = len(found) > limit
    found = found[:limit]
    return SensorUnitPage(items=await views.units_out(ctx, found),
                          next_after=found[-1]["_id"] if more else None)


@unit_router.post("", status_code=status.HTTP_201_CREATED)
async def create_unit(body: SensorUnitIn, user: Writer, ctx: CtxDep) -> SensorUnitOut:
    """A unit enters the inventory in stock (or in repair or retired); it reaches a station
    through `install`."""
    model = await models.require(ctx.db, body.model_id)
    serial = rules.normalize_serial(body.serial)
    now = ctx.clock.now()
    if body.last_calibrated_at is not None:
        rules.check_when(body.last_calibrated_at, now)
    doc = stamp({
        "_id": new_id(), "model_id": model["_id"], "serial": serial, "status": body.status,
        "current_station_id": None, "current_org_id": None, "current_parameter": None,
        "calibration_interval_days": body.calibration_interval_days,
        "last_calibrated_at": body.last_calibrated_at, "last_calibration_result": None,
        "needs_review": False, "flags": [], "notes": body.notes,
    }, now, user.id)
    doc["calibration_due_at"] = rules.due_at(body.last_calibrated_at,
                                             rules.interval_days(doc, model))
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        await units.insert(ctx.db, doc, s)
        await emitter.unit(ev.SensorUnitCreated, doc, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise SerialTaken() from exc
    return await views.unit_out(ctx, doc, now)


@unit_router.get("/{id}")
async def get_unit(id: IdPath, staff: Staff, ctx: CtxDep) -> SensorUnitDetail:
    unit = await units.require(ctx.db, id, staff)
    out = await views.unit_out(ctx, unit)
    rows = await history.unit_installations(ctx.db, id)
    return SensorUnitDetail(**out.model_dump(),
                            installations=await views.installations_out(ctx, rows))


@unit_router.patch("/{id}")
async def patch_unit(id: IdPath, body: SensorUnitPatch, user: Writer, ctx: CtxDep) -> SensorUnitOut:
    """Serial and model corrections (SEN-5 review), status in or out of stock, the interval
    override (CAL-3), notes. Installing and removing have their own actions."""
    current = await units.require(ctx.db, id)
    wanted: dict[str, Any] = {f: getattr(body, f) for f in body.model_fields_set - {"version"}}
    for field in ("model_id", "serial", "status", "needs_review"):
        if field in wanted and wanted[field] is None:
            del wanted[field]
    if "serial" in wanted:
        wanted["serial"] = rules.normalize_serial(wanted["serial"])
    changes = station_rules.changed_fields(current, wanted)
    if "status" in changes:
        rules.check_status_edit(current["status"], changes["status"])
    model = await models.require(ctx.db, changes.get("model_id", current["model_id"]))
    if {"model_id", "calibration_interval_days"} & changes.keys():
        due = rules.due_at(current.get("last_calibrated_at"),
                           rules.interval_days({**current, **changes}, model))
        if due != current.get("calibration_due_at"):
            changes["calibration_due_at"] = due
    if not changes:
        if body.version != current["version"]:
            raise VersionConflict()
        return await views.unit_out(ctx, current)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await units.update(
            ctx.db, id, changes, now=now, by=user.id, expected_version=body.version, session=s
        )
        await emitter.unit(ev.SensorUnitUpdated, updated, s, before=current,
                           changed_fields=sorted(changes))
        return updated

    try:
        updated = await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise SerialTaken() from exc
    return await views.unit_out(ctx, updated, now)


@unit_router.post("/{id}/install")
async def install_unit(id: IdPath, body: InstallIn, user: Writer, ctx: CtxDep) -> SensorUnitOut:
    """Put a unit in stock on a station (SEN-3). Visits do this through sensor actions
    (Phase 4); this is the manual inventory change."""
    unit = await units.require(ctx.db, id)
    model = await models.require(ctx.db, unit["model_id"])
    station = await stations.require(ctx.db, body.station_id)
    parameter = station_rules.normalize_parameter(body.parameter) if body.parameter else None
    occupied = {
        p for u in await units.installed_at(ctx.db, station["_id"])
        if (p := u.get("current_parameter"))
    }
    rules.check_install(unit, model, station, parameter, occupied)
    now = ctx.clock.now()
    at = body.at or now
    rules.check_when(at, now)
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await units.update(
            ctx.db, id,
            {"status": rules.UnitStatus.INSTALLED.value, "current_station_id": station["_id"],
             "current_org_id": station["owner_org_id"], "current_parameter": parameter},
            now=now, by=user.id, expected_version=body.version, session=s,
        )
        installation = stamp({
            "_id": new_id(), "sensor_unit_id": id, "station_id": station["_id"],
            "org_id": station["owner_org_id"], "parameter": parameter, "installed_at": at,
            "removed_at": None, "removal_reason": None, "installed_visit_id": None,
            "removed_visit_id": None, "source_action_id": None,
        }, now, user.id)
        await history.insert_installation(ctx.db, installation, s)
        await emitter.installation(ev.SensorInstalled, installation, updated, s, before=unit)
        return updated

    updated = await ctx.tx(save)
    return await views.unit_out(ctx, updated, now)


@unit_router.post("/{id}/remove")
async def remove_unit(id: IdPath, body: RemoveIn, user: Writer, ctx: CtxDep) -> SensorUnitOut:
    """Take a unit off its station, with the reason, into stock, repair or retirement."""
    unit = await units.require(ctx.db, id)
    if unit["status"] != rules.UnitStatus.INSTALLED:
        raise rules.UnitNotInstalled()
    opened = await history.open_installation(ctx.db, id)
    now = ctx.clock.now()
    at = body.at or now
    rules.check_when(at, now, not_before=opened["installed_at"] if opened else None)
    next_status: EditableUnitStatus = body.status
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await units.update(
            ctx.db, id,
            {"status": next_status, "current_station_id": None, "current_org_id": None,
             "current_parameter": None},
            now=now, by=user.id, expected_version=body.version, session=s,
        )
        if opened is not None:
            closed = await history.close_installation(
                ctx.db, opened["_id"], at=at, reason=body.reason, now=now, by=user.id,
                session=s,
            )
            await emitter.installation(ev.SensorRemoved, closed, updated, s, before=unit,
                                       reason=body.reason)
        else:  # pragma: no cover - an installed unit always has an open installation
            await emitter.unit(ev.SensorUnitUpdated, updated, s, before=unit,
                               changed_fields=["status"])
        return updated

    updated = await ctx.tx(save)
    return await views.unit_out(ctx, updated, now)
