"""Checklist templates (TRD §3.2 `/checklist-templates`; PRD VIS-8; AFD `/admin/checklists`; W10-11,
W10-12). Staff read, admins write. A template is never changed in place: saving writes the next
version, so a visit that copied version 3 keeps meaning version 3. Nothing is deleted; an
inactive template just stops being given to new visits."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, NotFound, ValidationFailed, VersionConflict
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.checklists.schemas import (
    Resolved,
    ResolvedItem,
    TemplateIn,
    TemplateList,
    TemplateOut,
    TemplatePatch,
)
from app.api.context import CtxDep
from app.domain.checklists import templates
from app.repo.checklists import templates as repo
from app.repo.stations import models, units
from app.repo.stations import stations as station_repo
from app.repo.stations.common import Db

router = APIRouter(prefix="/api/v1/checklist-templates", tags=["checklists"])

Reader = Annotated[User, Depends(require_roles("technician", "admin", "viewer"))]
Admin = Annotated[User, Depends(require_roles("admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]

TAKEN = "There is already an active template for that. Make it inactive first"


async def _model_names(db: Db, docs: list[dict[str, Any]]) -> dict[str, str]:
    ids = sorted({d["sensor_model_id"] for d in docs if d.get("sensor_model_id")})
    found = await models.by_ids(db, ids) if ids else {}
    return {i: f"{m['manufacturer']} {m['model']}" for i, m in found.items()}


async def _out(db: Db, doc: dict[str, Any]) -> TemplateOut:
    names = await _model_names(db, [doc])
    return TemplateOut.of(doc, names.get(doc.get("sensor_model_id") or ""))


def _same_items(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    def norm(items: list[dict[str, Any]]) -> list[tuple[Any, Any, Any]]:
        return [(i["id"], i["label"], i.get("help")) for i in items]

    return norm(a) == norm(b)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(body: TemplateIn, user: Admin, ctx: CtxDep) -> TemplateOut:
    """A new template for a station type, or an add-on for a sensor model."""
    station_type, model_id = templates.clean_scope(body.station_type, body.sensor_model_id)
    if model_id and await models.get(ctx.db, model_id) is None:
        raise ValidationFailed("That sensor model does not exist", code="unknown_model",
                               field="sensor_model_id")
    name = templates.clean_name(body.name)
    items = templates.clean_items([i.model_dump() for i in body.items], new_id)
    key = templates.scope_key(station_type, model_id)
    if await repo.active_for_scope(ctx.db, key) is not None:
        raise Conflict(TAKEN, code="template_exists")
    family = new_id()
    doc = {
        "_id": family, "family_id": family, "name": name, "station_type": station_type,
        "sensor_model_id": model_id, "scope_key": key, "version": 1, "items": items,
        "active": True, "is_current": True, "created_by": user.id,
        "created_at": ctx.clock.now(),
    }

    async def save(s: AsyncClientSession) -> None:
        await repo.insert(ctx.db, doc, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        raise Conflict(TAKEN, code="template_exists") from None
    return await _out(ctx.db, doc)


@router.get("")
async def list_templates(
    viewer: Reader, ctx: CtxDep, all_: Annotated[bool, Query(alias="all")] = False
) -> TemplateList:
    """The current version of each template. Inactive ones too, for an admin who asks (`all`)."""
    docs = await repo.list_current(ctx.db, active_only=not (all_ and viewer.is_admin))
    names = await _model_names(ctx.db, docs)
    return TemplateList(items=[
        TemplateOut.of(d, names.get(d.get("sensor_model_id") or "")) for d in docs
    ])


@router.get("/resolve")
async def resolve_for_station(
    viewer: Reader, ctx: CtxDep,
    station_id: Annotated[str, Query(pattern=UUID7_PATTERN)],
) -> Resolved:
    """What a visit to this station is given: its type's template, then an add-on for each
    sensor model installed there."""
    station = await station_repo.get(ctx.db, station_id)
    if station is None:
        raise NotFound()
    station_type = station.get("type")
    installed = await units.installed_at(ctx.db, station_id)
    model_ids = sorted({u["model_id"] for u in installed})
    found = await models.by_ids(ctx.db, model_ids) if model_ids else {}
    keys = [templates.scope_key(None, m) for m in model_ids]
    if station_type:
        keys.append(templates.scope_key(station_type, None))
    active = await repo.active_for_scopes(ctx.db, keys)
    station_template = (active.get(templates.scope_key(station_type, None))
                        if station_type else None)
    add_ons = [
        templates.AddOn(
            model_id=m,
            label=f"{found[m]['manufacturer']} {found[m]['model']}" if m in found else m,
            template=active.get(templates.scope_key(None, m)),
        )
        for m in model_ids
    ]
    return Resolved(
        station_id=station_id, station_type=station_type,
        items=[ResolvedItem(**i) for i in templates.resolve(station_template, add_ons)],
    )


@router.get("/{id}")
async def get_template(
    id: IdPath, viewer: Reader, ctx: CtxDep,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> TemplateOut:
    """The current version, or an older one by number (what a visit copied)."""
    doc = (await repo.at_version(ctx.db, id, version) if version is not None
           else await repo.current(ctx.db, id))
    if doc is None:
        raise NotFound()
    return await _out(ctx.db, doc)


@router.patch("/{id}")
async def change_template(
    id: IdPath, body: TemplatePatch, user: Admin, ctx: CtxDep
) -> TemplateOut:
    """Save the next version (name, items, or active). Nothing changed writes nothing."""
    current = await repo.current(ctx.db, id)
    if current is None:
        raise NotFound()
    if body.version != current["version"]:
        raise VersionConflict()
    name = templates.clean_name(body.name) if body.name is not None else current["name"]
    items = (templates.clean_items([i.model_dump() for i in body.items], new_id)
             if body.items is not None else current["items"])
    active = body.active if body.active is not None else current["active"]
    if (name == current["name"] and active == current["active"]
            and _same_items(items, current["items"])):
        return await _out(ctx.db, current)
    if active and not current["active"] and await repo.active_for_scope(
        ctx.db, current["scope_key"], excluding_family=id
    ) is not None:
        raise Conflict(TAKEN, code="template_exists")
    row = {
        **current, "_id": new_id(), "name": name, "items": items, "active": active,
        "version": current["version"] + 1, "is_current": True, "created_by": user.id,
        "created_at": ctx.clock.now(),
    }

    async def save(s: AsyncClientSession) -> None:
        await repo.retire(ctx.db, current["_id"], s)
        await repo.insert(ctx.db, row, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        raise Conflict(TAKEN, code="template_exists") from None
    return await _out(ctx.db, row)
