"""Runs a station import (PRD STN-8): plan every row, then write the valid ones.

Used by `POST /api/v1/stations/import` and `python -m app.cli import-stations`. Each station
is written in its own transaction with its sensors and their events, so one bad row never
blocks the rest and a failure leaves no half-written station.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mms_common.ids import new_id
from mms_common.mongo import in_transaction
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.domain.stations import importing, sensors
from app.domain.stations import stations as rules
from app.domain.stations.importing import SENSORS, STATIONS, Plan, RowError, SensorRow, StationRow
from app.events.publish import Emitter, ev
from app.repo.stations import history, models, orgs, stations, units
from app.repo.stations.common import stamp

Db = AsyncDatabase[dict[str, Any]]


@dataclass
class Report:
    dry_run: bool
    station_rows: int
    sensor_rows: int
    stations_created: int = 0
    sensors_created: int = 0
    models_created: int = 0
    skipped: list[RowError] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    warnings: list[RowError] = field(default_factory=list)


async def make_plan(db: Db, tables: dict[str, importing.Table], clock: Clock) -> Plan:
    station_table = tables.get(STATIONS, [])
    sensor_table = tables.get(SENSORS, [])
    codes = [
        rules.normalize_code(str(v))
        for _, row in station_table
        for name in importing.STATION_COLUMNS["code"]
        if (v := row.get(name)) not in (None, "")
    ]
    codes += [
        rules.normalize_code(str(v))
        for _, row in sensor_table
        for name in importing.SENSOR_COLUMNS["station_code"]
        if (v := row.get(name)) not in (None, "")
    ]
    return importing.plan(
        station_table,
        sensor_table,
        orgs_by_key=await orgs.active_by_key(db),
        existing_codes=await stations.by_codes(db, sorted(set(codes))),
        models_by_key=await models.by_key(db),
        units_by_model_serial=await units.by_model_serial(db),
        today=clock.now().date(),
    )


async def run(
    client: AsyncMongoClient[dict[str, Any]],
    db: Db,
    clock: Clock,
    emitter: Emitter,
    tables: dict[str, importing.Table],
    *,
    dry_run: bool,
    by: str | None,
) -> Report:
    plan = await make_plan(db, tables, clock)
    report = Report(
        dry_run=dry_run, station_rows=plan.station_rows, sensor_rows=plan.sensor_rows,
        skipped=plan.skipped, errors=list(plan.errors), warnings=plan.warnings,
    )
    existing_models = await models.by_key(db)
    if dry_run:
        report.stations_created = len(plan.stations)
        report.sensors_created = len(plan.sensors)
        report.models_created = len({s.model_key for s in plan.sensors} - existing_models.keys())
        return report

    now = clock.now()
    model_ids = {key: doc["_id"] for key, doc in existing_models.items()}
    model_docs = dict(existing_models)
    new_models = _new_models(plan.sensors, existing_models, now, by)
    if new_models:

        async def save_models(s: AsyncClientSession) -> None:
            for doc in new_models:
                await models.insert(db, doc, s)
                await emitter.sensor_model(ev.SensorModelCreated, doc, s)

        await in_transaction(client, save_models)
        report.models_created = len(new_models)
        for doc in new_models:
            model_ids[doc["key"]] = doc["_id"]
            model_docs[doc["key"]] = doc

    by_station: dict[str, list[SensorRow]] = {}
    for sensor in plan.sensors:
        by_station.setdefault(sensor.station_code, []).append(sensor)
    for row in plan.stations:
        rows = by_station.get(row.fields["code"], [])

        async def save(
            s: AsyncClientSession, row: StationRow = row, rows: list[SensorRow] = rows
        ) -> None:
            await _save_station(db, emitter, row, rows, model_docs, now, by, s)

        try:
            await in_transaction(client, save)
        except DuplicateKeyError:
            report.errors.append(RowError(
                STATIONS, row.row, "code",
                f"Station {row.fields['code']} or one of its serials was created meanwhile",
            ))
            continue
        report.stations_created += 1
        report.sensors_created += len(rows)
    report.errors.sort(key=lambda e: (e.sheet != STATIONS, e.row))
    return report


def _new_models(
    rows: list[SensorRow], existing: dict[str, dict[str, Any]], now: datetime, by: str | None
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.model_key in existing:
            continue
        doc = found.get(row.model_key)
        if doc is None:
            doc = found[row.model_key] = stamp({
                "_id": new_id(), "key": row.model_key, "kind": row.kind,
                "manufacturer": row.manufacturer, "model": row.model, "parameters": [],
                "default_calibration_interval_days": None,
            }, now, by)
        if row.parameter and row.parameter not in doc["parameters"]:
            doc["parameters"].append(row.parameter)
        if doc["default_calibration_interval_days"] is None:
            doc["default_calibration_interval_days"] = row.default_calibration_interval_days
    return list(found.values())


async def _save_station(
    db: Db,
    emitter: Emitter,
    row: StationRow,
    rows: list[SensorRow],
    model_docs: dict[str, dict[str, Any]],
    now: datetime,
    by: str | None,
    s: AsyncClientSession,
) -> None:
    station = stamp({
        "_id": new_id(), **row.fields, "photos": [], "qr_token": rules.new_qr_token(),
        "current_config_version": None,
    }, now, by)
    await stations.insert(db, station, s)
    await emitter.station(ev.StationCreated, station, s, via="import")
    for sensor in rows:
        model = model_docs[sensor.model_key]
        existing = await units.find_by_serial(db, model["_id"], sensor.serial, s)
        placed = {
            "status": sensors.UnitStatus.INSTALLED.value,
            "current_station_id": station["_id"],
            "current_org_id": station["owner_org_id"],
            "current_parameter": sensor.parameter,
        }
        calibration: dict[str, Any] = {}
        if sensor.last_calibrated_at is not None:
            calibration = {
                "last_calibrated_at": sensor.last_calibrated_at,
                "calibration_due_at": sensors.due_at(
                    sensor.last_calibrated_at,
                    sensor.calibration_interval_days
                    or model.get("default_calibration_interval_days"),
                ),
            }
        if existing is None:
            unit = stamp({
                "_id": new_id(), "model_id": model["_id"], "serial": sensor.serial,
                **placed, "calibration_interval_days": sensor.calibration_interval_days,
                "last_calibrated_at": None, "calibration_due_at": None,
                "last_calibration_result": None, "needs_review": False, "flags": [],
                "notes": None, **calibration,
            }, now, by)
            await units.insert(db, unit, s)
            await emitter.unit(ev.SensorUnitCreated, unit, s, via="import")
            before = None
        else:
            before = existing
            changes = {**placed, **calibration}
            if sensor.calibration_interval_days is not None:
                changes["calibration_interval_days"] = sensor.calibration_interval_days
            unit = await units.update(
                db, existing["_id"], changes, now=now, by=by,
                expected_version=existing["version"], session=s,
            )
        installation = stamp({
            "_id": new_id(), "sensor_unit_id": unit["_id"], "station_id": station["_id"],
            "org_id": station["owner_org_id"], "parameter": sensor.parameter,
            "installed_at": sensor.installed_at, "removed_at": None, "removal_reason": None,
            "installed_visit_id": None, "removed_visit_id": None, "source_action_id": None,
        }, now, by)
        await history.insert_installation(db, installation, s)
        await emitter.installation(ev.SensorInstalled, installation, unit, s, before=before)
