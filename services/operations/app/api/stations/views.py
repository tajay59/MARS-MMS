"""Response shapes that need more than one collection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mms_common.auth import User

from app.api.context import Ctx
from app.api.stations.schemas import InstallationOut, InstalledUnit, ModelSummary, SensorUnitOut
from app.domain.stations import sensors as rules
from app.repo.stations import history, models, stations, units


async def installed_units(ctx: Ctx, station_id: str, viewer: User) -> list[InstalledUnit]:
    found = await units.installed_at(ctx.db, station_id, viewer)
    model_docs = await models.by_ids(ctx.db, [u["model_id"] for u in found])
    opened = await history.open_at_station(ctx.db, station_id)
    now = ctx.clock.now()
    out: list[InstalledUnit] = []
    for unit in found:
        state = rules.due_state(unit.get("calibration_due_at"), now)
        installation = opened.get(unit["_id"])
        out.append(InstalledUnit(
            unit_id=unit["_id"], serial=unit["serial"], parameter=unit.get("current_parameter"),
            model=ModelSummary.of(model_docs.get(unit["model_id"]), unit["model_id"]),
            installed_at=installation["installed_at"] if installation else None,
            last_calibrated_at=unit.get("last_calibrated_at"),
            last_calibration_result=unit.get("last_calibration_result"),
            calibration_due_at=unit.get("calibration_due_at"),
            due_state=state.value if state else None,
            flags=list(unit.get("flags", [])),
        ))
    return out


async def installations_out(ctx: Ctx, rows: list[dict[str, Any]]) -> list[InstallationOut]:
    unit_docs = {
        u["_id"]: u
        for u in [await units.get(ctx.db, i) for i in {r["sensor_unit_id"] for r in rows}]
        if u is not None
    }
    model_docs = await models.by_ids(ctx.db, [u["model_id"] for u in unit_docs.values()])
    station_docs = await stations.by_ids(ctx.db, list({r["station_id"] for r in rows}))
    out: list[InstallationOut] = []
    for row in rows:
        unit = unit_docs.get(row["sensor_unit_id"], {})
        model_id = unit.get("model_id", "")
        station = station_docs.get(row["station_id"])
        out.append(InstallationOut(
            id=row["_id"], unit_id=row["sensor_unit_id"], serial=unit.get("serial", ""),
            model=ModelSummary.of(model_docs.get(model_id), model_id),
            station_id=row["station_id"], station_code=station["code"] if station else None,
            parameter=row.get("parameter"), installed_at=row["installed_at"],
            removed_at=row.get("removed_at"), removal_reason=row.get("removal_reason"),
            installed_visit_id=row.get("installed_visit_id"),
            removed_visit_id=row.get("removed_visit_id"),
        ))
    return out


async def unit_out(ctx: Ctx, unit: dict[str, Any], now: datetime | None = None) -> SensorUnitOut:
    model = await models.get(ctx.db, unit["model_id"])
    station_id = unit.get("current_station_id")
    station = await stations.get(ctx.db, station_id) if station_id else None
    return SensorUnitOut.of(unit, model, station, now or ctx.clock.now())


async def units_out(ctx: Ctx, found: list[dict[str, Any]]) -> list[SensorUnitOut]:
    model_docs = await models.by_ids(ctx.db, [u["model_id"] for u in found])
    station_docs = await stations.by_ids(
        ctx.db, [u["current_station_id"] for u in found if u.get("current_station_id")]
    )
    now = ctx.clock.now()
    return [
        SensorUnitOut.of(
            u, model_docs.get(u["model_id"]), station_docs.get(u.get("current_station_id") or ""),
            now,
        )
        for u in found
    ]
