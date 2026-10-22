"""Photos and video on a visit (TRD §3.2 `.../media`; PRD VIS-5, VIS-10; W11-10, W11-13).

The file is uploaded to the media service first, for `visit:{id}:station:{sid}:{phase}`; these
routes put it on the station. Anyone attending (or an admin) adds, captions and hides; the
uploader (or an admin) removes, until the report locks the visit. Photos are staff-only while the
visit is under way and shown to the client when it ends, except an item hidden again; an item
added after the end is shown at once. Each change, its event and the visibility request are one
Mongo transaction (rule 2).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, Forbidden
from mms_common.ids import UUID7_PATTERN
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import CtxDep
from app.api.visits.schemas import VisitOut
from app.domain.visits import media as rules
from app.events.publish import ev
from app.repo.requests import comments as file_repo
from app.repo.requests import requests as request_repo
from app.repo.visits import visits as repo

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])

Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


class MediaIn(BaseModel):
    """Put an uploaded file on a station. `media_id` is the upload's own id, so a retry after a
    lost answer attaches nothing twice."""

    model_config = ConfigDict(extra="forbid")

    media_id: Annotated[str, Field(pattern=UUID7_PATTERN)]
    phase: str
    caption: str | None = None
    captured_at: AwareDatetime | None = None


class MediaPatch(BaseModel):
    """Any of these. `caption: null` clears it; `hidden: true` keeps the item from the client."""

    model_config = ConfigDict(extra="forbid")

    caption: str | None = None
    hidden: bool | None = None


async def _context(
    ctx: Any, id: str, station_id: str, user: User
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    visit = await repo.require(ctx.db, id)
    station = dict(rules.station_of(visit, station_id))
    rules.check_can_change(visit, user.id, user.is_admin)
    request = await request_repo.require(ctx.db, visit["request_id"])
    return visit, station, request


async def _reread(
    ctx: Any, id: str, station_id: str, user: User, s: AsyncClientSession
) -> dict[str, Any]:
    """A guarded write found nothing to change: read the visit to say why."""
    fresh = await repo.require(ctx.db, id, None, s)
    rules.station_of(fresh, station_id)
    rules.check_can_change(fresh, user.id, user.is_admin)
    return fresh


@router.post("/{id}/stations/{station_id}/media")
async def add_media(
    id: IdPath, station_id: IdPath, body: MediaIn, user: Worker, ctx: CtxDep
) -> VisitOut:
    """VIS-5: a photo or video, for a phase of the visit at this station."""
    visit, station, request = await _context(ctx, id, station_id, user)
    phase = rules.check_phase(body.phase)
    if any(e["media_id"] == body.media_id for e in station.get("media", [])):
        return VisitOut.build(visit, request, user)  # already there: a retry
    now = ctx.clock.now()
    caption = rules.check_caption(body.caption)
    captured_at = rules.check_captured_at(body.captured_at, now)
    facts = rules.check_file(
        await file_repo.file_facts(ctx.media, body.media_id, ctx.request_id),
        owner=rules.owner_ref(id, station_id, phase), user_id=user.id,
    )
    entry = rules.new_entry(
        facts, media_id=body.media_id, phase=phase, caption=caption, captured_at=captured_at,
        by=user.id, by_name=user.name, now=now,
    )
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.add_media(ctx.db, id, station_id, entry, now=now, by=user.id,
                                       session=s)
        if updated is None:
            holder["doc"] = await _reread(ctx, id, station_id, user, s)  # else: it just got there
            return
        if rules.shared(updated):
            await emitter.visit_visibility([body.media_id], "org", updated, s)
        await emitter.visit(
            ev.VisitMediaChanged, "visit.media_changed", updated, request, s, before=visit,
            station_id=station_id, media_id=body.media_id, phase=phase, kind=facts.kind,
            change="added",
        )
        holder["doc"] = updated

    await ctx.tx(save)
    return VisitOut.build(holder["doc"], request, user)


@router.patch("/{id}/stations/{station_id}/media/{media_id}")
async def change_media(
    id: IdPath, station_id: IdPath, media_id: IdPath, body: MediaPatch, user: Worker,
    ctx: CtxDep,
) -> VisitOut:
    """A caption, or hide an item from the client (W11-13) and show it again."""
    visit, station, request = await _context(ctx, id, station_id, user)
    entry = rules.entry_of(station, media_id)
    fields: dict[str, Any] = {}
    changes: list[str] = []
    if "caption" in body.model_fields_set:
        caption = rules.check_caption(body.caption)
        if caption != entry.get("caption"):
            fields["caption"] = caption
            changes.append("captioned")
    if body.hidden is not None and body.hidden != bool(entry.get("hidden")):
        fields["hidden"] = body.hidden
        changes.append("hidden" if body.hidden else "shown")
    if not fields:
        return VisitOut.build(visit, request, user)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.change_media(ctx.db, id, station_id, media_id, fields, now=now,
                                          by=user.id, session=s)
        if updated is None:
            fresh = await _reread(ctx, id, station_id, user, s)
            rules.entry_of(rules.station_of(fresh, station_id), media_id)
            raise Conflict("This visit was just changed by someone else. Reload and try again",
                           code="visit_changed")
        for change in changes:
            if change in ("hidden", "shown") and rules.shared(updated):
                await emitter.visit_visibility(
                    [media_id], "staff" if change == "hidden" else "org", updated, s)
            await emitter.visit(
                ev.VisitMediaChanged, "visit.media_changed", updated, request, s, before=visit,
                station_id=station_id, media_id=media_id, phase=entry["phase"],
                kind=entry["kind"], change=change,
            )
        holder["doc"] = updated

    await ctx.tx(save)
    return VisitOut.build(holder["doc"], request, user)


@router.delete("/{id}/stations/{station_id}/media/{media_id}")
async def remove_media(
    id: IdPath, station_id: IdPath, media_id: IdPath, user: Worker, ctx: CtxDep
) -> VisitOut:
    """Take a photo or video off the visit and delete the file: the person who added it, or an
    admin, until the report locks the visit."""
    visit, station, request = await _context(ctx, id, station_id, user)
    entry = rules.entry_of(station, media_id)
    if not (user.is_admin or entry["added_by"] == user.id):
        raise Forbidden("Only the person who added it can remove it", code="not_uploader")
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.remove_media(ctx.db, id, station_id, media_id, now=now, by=user.id,
                                          session=s)
        if updated is None:
            fresh = await _reread(ctx, id, station_id, user, s)
            holder["doc"] = fresh  # it was just removed by someone else: nothing left to do
            return
        await emitter.media_deletion([media_id], "removed_from_visit", updated, request, s)
        await emitter.visit(
            ev.VisitMediaChanged, "visit.media_changed", updated, request, s, before=visit,
            station_id=station_id, media_id=media_id, phase=entry["phase"], kind=entry["kind"],
            change="removed",
        )
        holder["doc"] = updated

    await ctx.tx(save)
    return VisitOut.build(holder["doc"], request, user)

