"""Writing what `domain/visits/reconcile.py` planned (TRD §3.2.3; W11-5 to W11-9).

`reconcile_station` is called inside the transaction that ends a visit or saves a work record
after it has ended, so the inventory, the application rows, the events and the record move
together: a correction that is refused (`sensor_changed_later`, a serial that is not at the
station) raises and the whole transaction writes nothing. Configuration versions are created the
same way, once each, from the work record.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mms_common.errors import Conflict, ValidationFailed
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx
from app.api.stations.document_routes import file_facts
from app.domain.stations import documents as doc_rules
from app.domain.visits import reconcile
from app.events.publish import Emitter, ev
from app.repo.stations import documents as config_repo
from app.repo.stations import history, models, units
from app.repo.stations import stations as station_repo
from app.repo.stations.common import stamp
from app.repo.visits import applications as app_repo

REVERSAL = "Undone: the sensor action was changed or removed"


async def reconcile_station(
    ctx: Ctx, user: Any, visit: dict[str, Any], station_id: str, actions: list[dict[str, Any]],
    s: AsyncClientSession, emitter: Emitter,
) -> reconcile.Plan:
    """Make the inventory agree with this station's sensor actions."""
    db, now = ctx.db, ctx.clock.now()
    applications = await app_repo.for_station(db, visit["_id"], station_id, s)
    if not actions and not applications:
        return reconcile.Plan()
    station = await station_repo.require(db, station_id, None, s)
    visit_station = next(st for st in visit["stations"] if st["station_id"] == station_id)

    loaded: dict[str, dict[str, Any]] = {}
    wanted_ids = list({e["unit_id"] for a in applications for e in a["effects"]["units"]})
    for found in (
        await units.by_ids(db, wanted_ids, s) if wanted_ids else [],
        await units.by_serials(db, sorted(reconcile.serials_in(actions)), s)
        if reconcile.serials_in(actions) else [],
        await units.installed_at(db, station_id, None, s),
    ):
        loaded.update({u["_id"]: u for u in found})
    model_ids = {u["model_id"] for u in loaded.values()} | {
        a["sensor_model_id"] for a in actions if a.get("sensor_model_id")}
    known_models = await models.by_ids(db, sorted(model_ids), s) if model_ids else {}
    install_ids = list({
        c["installation_id"] for a in applications for k in ("opened", "closed")
        for c in a["effects"][k]
    })
    installations = {i["_id"]: i for i in await history.open_at_station_in(db, station_id, s)}
    if install_ids:
        installations.update({i["_id"]: i for i in
                              await history.installations_by_ids(db, install_ids, s)})

    # The work is taken to have happened when the owner arrived (never in the future)
    at = min(visit_station.get("arrived_at") or visit.get("started_at") or now, now)
    world = reconcile.World.of(station, list(loaded.values()), known_models,
                               list(installations.values()), now, user.name)
    plan = reconcile.plan(
        world, reconcile.Context(visit, visit_station, user.id, at), actions, applications
    )
    await _run(ctx, user, visit, station, plan, loaded, s, emitter)
    return plan


async def _run(
    ctx: Ctx, user: Any, visit: dict[str, Any], station: dict[str, Any], plan: reconcile.Plan,
    loaded: dict[str, dict[str, Any]], s: AsyncClientSession, emitter: Emitter,
) -> None:
    db, now = ctx.db, ctx.clock.now()
    current = dict(loaded)
    station_id = station["_id"]

    async def update(
        unit_id: str, changes: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        before = current[unit_id]
        after = await units.update(db, unit_id, changes, now=now, by=user.id,
                                   expected_version=int(before["version"]), session=s)
        current[unit_id] = after
        return before, after

    for step in plan.steps:
        d = step.data
        match step.op:
            case "create_unit":
                await units.insert(db, d["doc"], s)
                current[d["doc"]["_id"]] = d["doc"]
                await emitter.unit(ev.SensorUnitCreated, d["doc"], s, via="visit")
            case "install":
                before, after = await update(d["unit_id"], d["changes"])
                await history.insert_installation(db, d["installation"], s)
                await emitter.installation(ev.SensorInstalled, d["installation"], after, s,
                                           before=before)
            case "remove":
                before, after = await update(d["unit_id"], d["changes"])
                closed = await history.close_installation(
                    db, d["installation_id"], at=d["at"], reason=d["reason"], now=now,
                    by=user.id, session=s, visit_id=d["removed_visit_id"],
                )
                await emitter.installation(ev.SensorRemoved, closed, after, s, before=before,
                                           reason=d["reason"])
            case "calibrate":
                after = current[d["unit_id"]]
                if d["changes"]:
                    _, after = await update(d["unit_id"], d["changes"])
                await history.insert_calibration(db, d["calibration"], s)
                await emitter.calibration(d["calibration"], after, s)
            case "restore_unit":
                before, after = await update(d["unit_id"], d["changes"])
                await emitter.unit(ev.SensorUnitUpdated, after, s, before=before,
                                   changed_fields=sorted(d["changes"]))
            case "undo_create":
                await units.delete(db, d["unit_id"], s)
                current.pop(d["unit_id"], None)
            case "reopen":
                await history.reopen_installation(db, d["installation_id"], now=now, by=user.id,
                                                  session=s)
            case "undo_installation":
                await history.delete_installation(db, d["installation_id"], s)
            case "void_calibration":
                voided = await history.void_calibration(db, d["calibration_id"], now=now,
                                                        by=user.id, session=s)
                await emitter.calibration_voided(
                    voided, current.get(voided["sensor_unit_id"]), s, reason=REVERSAL)
            case "forget":
                await app_repo.delete(db, d["action_id"], s)
                await emitter.application_reversed(
                    visit, station_id, d["action_id"], d["unit_ids"], station, s)
            case "remember":
                seq = await app_repo.next_seq(db, visit["_id"], station_id, s)
                await app_repo.insert(db, app_repo.row(
                    d["action_id"], visit["_id"], station_id, seq, d["action_hash"],
                    d["effects"], now), s)
            case _:  # pragma: no cover - the planner makes only these
                raise RuntimeError(f"unknown step {step.op}")


# --- Configuration versions (CFG-1, CFG-2, CFG-4; W11-9) -----------------------------------------


async def check_config(
    ctx: Ctx, visit: dict[str, Any], visit_station: dict[str, Any], entries: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], list[Any]]]:
    """Before the transaction (it asks media about each file): which entries are new, with their
    files checked. An entry already made is left alone, and refused if it now says something
    else, because a created version never changes (CFG-2)."""
    todo: list[tuple[dict[str, Any], list[Any]]] = []
    station_id = visit_station["station_id"]
    owner = visit_station["owner_staff_id"]
    for entry in entries:
        existing = await config_repo.version_by_id(ctx.db, entry["id"])
        if existing is not None:
            if existing["station_id"] != station_id or [
                f["media_id"] for f in existing["files"]
            ] != list(entry["files"]):
                raise Conflict("A configuration version that was created can't be changed. "
                               "Add a new one", code="config_version_immutable",
                               field="config_versions", version_id=entry["id"])
            continue
        found = await asyncio.gather(*(file_facts(ctx, m) for m in entry["files"]))
        checked = [
            doc_rules.check_file(
                f, owner=doc_rules.config_owner_ref(station_id), kinds=doc_rules.CONFIG_KINDS,
                user_id=owner, ready_only=True, field="config_versions",
            )
            for f in found
        ]
        doc_rules.check_unique_names(checked)
        for media_id in entry["files"]:
            if await config_repo.version_with_file(ctx.db, media_id) is not None:
                raise ValidationFailed(
                    "A file is already part of a configuration version", code="file_in_use",
                    field="config_versions", media_id=media_id,
                )
        todo.append((entry, checked))
    return todo


async def create_config(
    ctx: Ctx, user: Any, visit: dict[str, Any], visit_station: dict[str, Any],
    todo: list[tuple[dict[str, Any], list[Any]]], s: AsyncClientSession, emitter: Emitter,
) -> None:
    now = ctx.clock.now()
    station = await station_repo.require(ctx.db, visit_station["station_id"], None, s)
    for entry, checked in todo:
        number = await config_repo.next_version(ctx.db, station["_id"], s)
        doc = {**stamp({
            "_id": entry["id"], "station_id": station["_id"],
            "files": [
                {"media_id": m, "filename": f.filename, "sha256": f.checksum_sha256,
                 "size_bytes": f.size_bytes}
                for m, f in zip(entry["files"], checked, strict=True)
            ],
            "notes": entry.get("notes"), "visit_id": visit["_id"],
            "created_by_name": user.name,
        }, now, user.id), "version": number}
        await config_repo.insert_version(ctx.db, doc, s)
        await emitter.config_version(doc, station, s)
