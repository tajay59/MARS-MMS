"""Stations (TRD §3.2 stations module; PRD STN-1 to STN-8, ORG-2, ORG-3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, ValidationFailed, VersionConflict
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import CtxDep
from app.api.stations import views
from app.api.stations.schemas import (
    ImportProblem,
    ImportReport,
    InstallationOut,
    OrgOption,
    Places,
    StationDetail,
    StationFacets,
    StationIn,
    StationPage,
    StationPatch,
    StationStatus,
    StationSummary,
)
from app.domain.stations import importing, places
from app.domain.stations import stations as rules
from app.events.publish import ev
from app.jobs import station_import
from app.repo.stations import history, orgs, units
from app.repo.stations import stations as repo
from app.repo.stations.common import stamp

router = APIRouter(prefix="/api/v1/stations", tags=["stations"])

Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client their own org
Writer = Annotated[User, Depends(require_roles("technician", "admin"))]
Admin = Annotated[User, Depends(require_roles("admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
MAX_IMPORT_BYTES = 10 * 1024 * 1024


class CodeTaken(Conflict):
    code, title = "code_taken", "A station with this code already exists"


class ExternalIdTaken(Conflict):
    code, title = "external_id_taken", "Another station has this external ID"


def _station_conflict(exc: DuplicateKeyError) -> Conflict:
    """Which unique field clashed: the code or the external ID."""
    pattern = (exc.details or {}).get("keyPattern") or {}
    return ExternalIdTaken() if "external_id" in pattern else CodeTaken()


class ParameterInUse(Conflict):
    code, title = "parameter_in_use", "A sensor installed here measures this parameter"


@router.get("")
async def list_stations(
    viewer: Reader,
    ctx: CtxDep,
    org_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    country: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
    type_: Annotated[str | None, Query(alias="type", max_length=60)] = None,
    status_: Annotated[StationStatus | None, Query(alias="status")] = None,
    parameter: Annotated[str | None, Query(max_length=rules.PARAMETER_MAX_LENGTH)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    after: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> StationPage:
    """STN-5. Sorted by code; pass the last code as `after` for the next page."""
    filters = repo.Filters(
        org_id=org_id, country=country, type=type_, status=status_,
        parameter=parameter.upper() if parameter else None, q=q,
    )
    found, total = await repo.search(ctx.db, viewer, filters, after=after, limit=limit + 1)
    more = len(found) > limit
    found = found[:limit]
    due = await units.next_due_by_station(ctx.db, [d["_id"] for d in found])
    return StationPage(
        items=[StationSummary.of(d, due.get(d["_id"])) for d in found],
        total=total,
        next_after=found[-1]["code"] if more else None,
    )


@router.get("/facets")
async def station_facets(viewer: Reader, ctx: CtxDep) -> StationFacets:
    """The values the list's filters offer (STN-5)."""
    found = await repo.facets(ctx.db, viewer)
    options: list[OrgOption] = []
    if not viewer.is_client:
        for org_id in found["org_ids"]:
            org = await orgs.get(ctx.db, org_id)
            options.append(OrgOption(id=org_id, name=org["name"] if org else org_id))
        options.sort(key=lambda o: o.name.casefold())
    return StationFacets(
        countries=found["countries"], types=found["types"], parameters=found["parameters"],
        organizations=options,
    )


@router.get("/places")
async def station_places(_: Writer) -> Places:
    """Each country's time zones, for the station form (a one-zone country gets it filled in)."""
    zones = places.zones_by_country()
    return Places(time_zones={code: list(found) for code, found in zones.items()})


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_station(body: StationIn, user: Writer, ctx: CtxDep) -> StationDetail:
    """STN-1. The owner organization is fixed for good (ORG-2, BSD B5)."""
    code = rules.check_code(body.code)
    rules.check_place(body.country, body.time_zone)
    org = await orgs.get(ctx.db, body.owner_org_id)
    if org is None or org["status"] != "active":
        raise ValidationFailed("Choose an active organization", code="org_inactive",
                               field="owner_org_id")
    now = ctx.clock.now()
    doc = stamp({
        "_id": new_id(), "code": code, "name": body.name, "type": body.type,
        "external_id": body.external_id,
        "owner_org_id": org["_id"], "owner_org_name": org["name"], "country": body.country,
        "time_zone": body.time_zone, "region": body.region,
        "location": rules.point(body.latitude, body.longitude), "elevation_m": body.elevation_m,
        "parameters": rules.check_parameters(body.parameters),
        "logger": _dump(body.logger), "comms": _dump(body.comms), "power": _dump(body.power),
        "install_date": body.install_date.isoformat() if body.install_date else None,
        "status": body.status, "access_notes": body.access_notes, "photos": [],
        "qr_token": rules.new_qr_token(), "current_config_version": None,
    }, now, user.id)
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        await repo.insert(ctx.db, doc, s)
        await emitter.station(ev.StationCreated, doc, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise _station_conflict(exc) from exc
    return StationDetail.build(doc, user, [], None)


@router.post("/import")
async def import_stations(
    admin: Admin,
    ctx: CtxDep,
    stations: Annotated[UploadFile, File(
        description="XLSX workbook, stations CSV, or the existing system's site export (JSON)"
    )],
    sensors: Annotated[UploadFile | None, File(description="Sensors CSV")] = None,
    dry_run: Annotated[bool, Query()] = True,
) -> ImportReport:
    """STN-8. A dry run (the default) only reports; valid rows are imported otherwise."""
    try:
        tables = importing.read_file(stations.filename or "", await _read(stations))
        if sensors is not None:
            sensor_tables = importing.read_file(sensors.filename or "", await _read(sensors))
            tables[importing.SENSORS] = sensor_tables[importing.STATIONS]
        report = await station_import.run(
            ctx.client, ctx.db, ctx.clock, ctx.emitter(admin), tables, dry_run=dry_run,
            by=admin.id,
        )
    except importing.SheetError as exc:
        raise ValidationFailed(str(exc), code="unreadable_file") from exc
    return ImportReport(
        dry_run=report.dry_run, station_rows=report.station_rows,
        sensor_rows=report.sensor_rows, stations_created=report.stations_created,
        sensors_created=report.sensors_created, models_created=report.models_created,
        skipped=[ImportProblem(**vars(p)) for p in report.skipped],
        errors=[ImportProblem(**vars(p)) for p in report.errors],
        warnings=[ImportProblem(**vars(p)) for p in report.warnings],
    )


@router.get("/{id}")
async def get_station(id: IdPath, viewer: Reader, ctx: CtxDep) -> StationDetail:
    """STN-4, STN-6: details with installed units; clients see their own stations only."""
    doc = await repo.require(ctx.db, id, viewer)
    installed = await views.installed_units(ctx, id, viewer)
    due = min((u.calibration_due_at for u in installed if u.calibration_due_at), default=None)
    return StationDetail.build(doc, viewer, installed, due)


@router.patch("/{id}")
async def patch_station(id: IdPath, body: StationPatch, user: Writer, ctx: CtxDep) -> StationDetail:
    current = await repo.require(ctx.db, id)
    wanted: dict[str, Any] = {}
    for field in body.model_fields_set - {"version", "latitude", "longitude"}:
        value = getattr(body, field)
        if field in ("logger", "comms", "power"):
            value = _dump(value)
        elif field == "install_date":
            value = value.isoformat() if value else None
        elif field == "code":
            value = rules.check_code(value)
        elif field == "parameters":
            value = rules.check_parameters(value or [])
        elif value is None and field in ("name", "country", "time_zone", "status"):
            raise ValidationFailed(f"{field} can't be empty", code="required", field=field)
        wanted[field] = value
    if body.latitude is not None and body.longitude is not None:
        wanted["location"] = rules.point(body.latitude, body.longitude)
    changes = rules.changed_fields(current, wanted)
    if "country" in changes or "time_zone" in changes:
        rules.check_place(changes.get("country", current["country"]),
                          changes.get("time_zone", current["time_zone"]))
    if "parameters" in changes:
        measured: set[str] = {
            p for u in await units.installed_at(ctx.db, id) if (p := u.get("current_parameter"))
        }
        if missing := measured - set(changes["parameters"]):
            raise ParameterInUse(f"Remove the sensor for {', '.join(sorted(missing))} first")
    if not changes:
        if body.version != current["version"]:
            raise VersionConflict()
        return await get_station(id, user, ctx)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await repo.update(
            ctx.db, id, changes, now=now, by=user.id, expected_version=body.version, session=s
        )
        await emitter.station(ev.StationUpdated, updated, s, before=current,
                              changed_fields=sorted(changes))
        return updated

    try:
        updated = await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise _station_conflict(exc) from exc
    installed = await views.installed_units(ctx, id, user)
    due = min((u.calibration_due_at for u in installed if u.calibration_due_at), default=None)
    return StationDetail.build(updated, user, installed, due)


@router.get("/{id}/installations")
async def station_installations(
    id: IdPath, viewer: Reader, ctx: CtxDep
) -> list[InstallationOut]:
    """SEN-3: which unit sat here, for which parameter, and when."""
    await repo.require(ctx.db, id, viewer)
    rows = await history.station_installations(ctx.db, id, viewer)
    return await views.installations_out(ctx, rows)


def _dump(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    data: dict[str, Any] = value.model_dump()
    return data if any(v is not None for v in data.values()) else None


async def _read(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise ValidationFailed("The file is larger than 10 MB", code="file_too_large")
    return content
