"""A station's board on a visit: Notes, Tasks, Recommendations and Config (TRD §3.2.3; PRD VIS-5,
VIS-7; decisions W11-16 to W11-35).

Anyone attending (or an admin) adds an element; its author, the station's owner or an admin
changes it, from the visit's start until its report locks it. Each element is saved on its own
with the version the editor saw, so a stale save is a conflict for that element only (ADR-18: no
merge). Files are uploaded to the media service first, for
`visit:{id}:station:{sid}:element:{eid}:{section}`, then put on the element. Every change, its
events and any visibility request are one Mongo transaction (rule 2).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, NotFound
from mms_common.ids import UUID7_PATTERN
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import Ctx, CtxDep
from app.api.visits.element_schemas import (
    ElementIn,
    ElementList,
    ElementMediaIn,
    ElementMediaPatch,
    ElementOut,
    ElementPut,
    ItemBody,
)
from app.domain.visits import elements as rules
from app.events.publish import Emitter, ev
from app.repo.requests import comments as file_repo
from app.repo.requests import requests as request_repo
from app.repo.visits import elements as repo
from app.repo.visits import visits as visit_repo

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])

Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client their own org
Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]

BOARD = "/{id}/stations/{station_id}/elements"
ONE = BOARD + "/{element_id}"


def _is_open(visit: dict[str, Any]) -> bool:
    try:
        rules.check_open(visit)
    except Conflict:
        return False
    return True


def _out(doc: dict[str, Any], visit: dict[str, Any], station: Any, viewer: User) -> ElementOut:
    return ElementOut.build(doc, dict(station), viewer, open_=_is_open(visit))


async def _board(
    ctx: Ctx, id: str, station_id: str, viewer: User | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The visit (a client's own organization only) and its station, or not found."""
    visit = await visit_repo.require(ctx.db, id, viewer)
    return visit, dict(rules.station_of(visit, station_id))


async def _element(
    ctx: Ctx, visit: dict[str, Any], station_id: str, element_id: str,
    session: AsyncClientSession | None = None,
) -> dict[str, Any]:
    """The element on this station of this visit, tombstone included."""
    doc = await repo.get(ctx.db, element_id, None, session)
    if doc is None or doc["visit_id"] != visit["_id"] or doc["station_id"] != station_id:
        raise NotFound()
    return doc


def _changed(doc: dict[str, Any], visit: dict[str, Any], station: Any, viewer: User) -> Conflict:
    """The editor saw an older version: say so, with what is saved now (TRD §7.4)."""
    return Conflict("This was changed on another device. Look at the saved copy",
                    code="element_changed",
                    current=_out(doc, visit, station, viewer).model_dump(mode="json"))


def _items(body: list[ItemBody]) -> list[rules.ItemIn]:
    return [rules.ItemIn(id=i.id, text=i.text, done=i.done) for i in body]


async def _share(
    ctx: Ctx, emitter: Emitter, visit: dict[str, Any], to_org: list[str], to_staff: list[str],
    s: AsyncClientSession,
) -> None:
    """Show files to the client or take them back, numbered by the visit (W11-28)."""
    for media_ids, visibility in ((to_org, "org"), (to_staff, "staff")):
        if media_ids:
            seq = await visit_repo.next_visibility_seq(ctx.db, visit["_id"], s)
            await emitter.visit_visibility(media_ids, visibility, visit, s, version=seq)


# --- Reading ------------------------------------------------------------------------------------


@router.get(BOARD)
async def list_elements(id: IdPath, station_id: IdPath, viewer: Reader, ctx: CtxDep) -> ElementList:
    """A station's board, newest first. A client sees the shared elements once the visit has
    ended, and nothing before (W11-28)."""
    visit, station = await _board(ctx, id, station_id, viewer)
    if viewer.is_client and not rules.ended(visit):
        docs: list[dict[str, Any]] = []
    else:
        docs = await repo.for_station(ctx.db, id, station_id, viewer)
    can_add = (not viewer.is_client and "viewer" not in viewer.roles and _is_open(visit)
               and (viewer.is_admin or viewer.id in visit["staff_ids"]))
    return ElementList(items=[_out(d, visit, station, viewer) for d in docs], can_add=can_add)


@router.get(ONE)
async def get_element(
    id: IdPath, station_id: IdPath, element_id: IdPath, viewer: Reader, ctx: CtxDep
) -> ElementOut:
    visit, station = await _board(ctx, id, station_id, viewer)
    doc = await repo.get(ctx.db, element_id, viewer)
    if (doc is None or doc["visit_id"] != id or doc["station_id"] != station_id
            or doc.get("deleted_at") is not None
            or (viewer.is_client and not rules.visible_to_client(visit, doc))):
        raise NotFound()
    return _out(doc, visit, station, viewer)


# --- Adding, saving, deleting -------------------------------------------------------------------


@router.post(BOARD, status_code=status.HTTP_201_CREATED)
async def add_element(
    id: IdPath, station_id: IdPath, body: ElementIn, user: Worker, ctx: CtxDep,
    response: Response,
) -> ElementOut:
    """VIS-5, VIS-7: a Note, Task, Recommendation or Config on the station's board. Sending the
    same `id` and content again returns the element that was made (200)."""
    visit, station = await _board(ctx, id, station_id)
    now = ctx.clock.now()

    def fields_for(previous: dict[str, Any] | None) -> dict[str, Any]:
        return rules.content(
            body.kind, title=body.title, description=body.description, items=_items(body.items),
            priority=body.priority, shared=body.shared, previous=previous, user_id=user.id,
            now=now,
        )

    def replay(existing: dict[str, Any]) -> ElementOut:
        """The same `id` again: the element it made, if this is that element; else a refusal."""
        if existing.get("deleted_at") is not None and existing["created_by"] == user.id:
            raise Conflict("This was deleted", code="element_deleted")
        if (existing["created_by"] != user.id or existing["visit_id"] != id
                or existing["station_id"] != station_id or existing["kind"] != body.kind
                or not rules.same_content(existing, fields_for(existing))):
            raise Conflict("That ID is already used", code="duplicate_id")
        response.status_code = status.HTTP_200_OK
        return _out(existing, visit, station, user)

    existing = await repo.get(ctx.db, body.id)
    if existing is not None:
        return replay(existing)
    rules.check_can_create(visit, user.id, user.is_admin)
    fields = fields_for(None)
    request = await request_repo.require(ctx.db, visit["request_id"])
    doc = rules.new_element(
        element_id=body.id, visit=visit, station_id=station_id, org_id=visit["org_id"],
        kind=body.kind, fields=fields, user_id=user.id, user_name=user.name,
        device_id=body.device_id, now=now,
    )
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        rules.check_room(await repo.count_for_station(ctx.db, id, station_id, s))
        await repo.insert(ctx.db, doc, s)
        await emitter.element(ev.VisitElementAdded, "visit.element_added", doc, visit, request,
                              s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        # The same `id` arrived twice at once: the other one won
        won = await repo.get(ctx.db, body.id)
        if won is None:
            raise
        return replay(won)
    return _out(doc, visit, station, user)


@router.put(ONE)
async def save_element(
    id: IdPath, station_id: IdPath, element_id: IdPath, body: ElementPut, user: Worker,
    ctx: CtxDep,
) -> ElementOut:
    """The whole content, against `base_version` (W11-26). A save that says what is already
    saved succeeds whatever its version: it is a retry after a lost answer."""
    visit, station = await _board(ctx, id, station_id)
    doc = await _element(ctx, visit, station_id, element_id)
    rules.check_alive(doc)
    rules.check_can_edit(visit, station, doc, user.id, user.is_admin)
    now = ctx.clock.now()
    fields = rules.content(
        doc["kind"], title=body.title, description=body.description, items=_items(body.items),
        priority=body.priority, shared=body.shared, previous=doc, user_id=user.id, now=now,
    )
    if rules.same_content(doc, fields):
        return _out(doc, visit, station, user)
    if body.base_version != doc["version"]:
        raise _changed(doc, visit, station, user)
    changed = rules.changed_fields(doc, fields)
    request = await request_repo.require(ctx.db, visit["request_id"])
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.save_content(
            ctx.db, element_id, fields, base_version=body.base_version, now=now, by=user.id,
            device_id=body.device_id, session=s,
        )
        if updated is None:
            fresh = await _element(ctx, visit, station_id, element_id, s)
            rules.check_alive(fresh)
            raise _changed(fresh, visit, station, user)
        current = await visit_repo.require(ctx.db, id, None, s)
        to_org, to_staff = rules.sharing_change(current, doc, updated)
        await _share(ctx, emitter, current, to_org, to_staff, s)
        await emitter.element(ev.VisitElementUpdated, "visit.element_updated", updated, current,
                              request, s, before=doc, changed_fields=changed)
        holder["doc"] = updated

    await ctx.tx(save)
    return _out(holder["doc"], visit, station, user)


@router.delete(ONE, status_code=status.HTTP_204_NO_CONTENT)
async def delete_element(
    id: IdPath, station_id: IdPath, element_id: IdPath, user: Worker, ctx: CtxDep,
    base_version: Annotated[int, Query(ge=1)],
) -> None:
    """Take an element off the board and delete its files. A tombstone stays, so a late save
    from another device cannot bring it back (W11-26). Deleting it again changes nothing."""
    visit, station = await _board(ctx, id, station_id)
    doc = await _element(ctx, visit, station_id, element_id)
    if doc.get("deleted_at") is not None:
        return
    rules.check_can_edit(visit, station, doc, user.id, user.is_admin)
    if base_version != doc["version"]:
        raise _changed(doc, visit, station, user)
    now = ctx.clock.now()
    request = await request_repo.require(ctx.db, visit["request_id"])
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        gone = await repo.tombstone(ctx.db, element_id, base_version=base_version, now=now,
                                    by=user.id, session=s)
        if gone is None:
            fresh = await _element(ctx, visit, station_id, element_id, s)
            if fresh.get("deleted_at") is not None:
                return  # someone deleted it a moment ago: nothing left to do
            raise _changed(fresh, visit, station, user)
        current = await visit_repo.require(ctx.db, id, None, s)
        _, to_staff = rules.sharing_change(current, doc, None)
        await _share(ctx, emitter, current, [], to_staff, s)
        files = rules.all_media_ids(doc)
        if files:
            await emitter.media_deletion(files, "removed_from_visit", current, request, s)
        await emitter.element(ev.VisitElementDeleted, "visit.element_deleted", gone, current,
                              request, s, before=doc)

    await ctx.tx(save)


# --- Files (W11-27) -----------------------------------------------------------------------------


async def _editable(
    ctx: Ctx, id: str, station_id: str, element_id: str, user: User
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    visit, station = await _board(ctx, id, station_id)
    doc = await _element(ctx, visit, station_id, element_id)
    rules.check_alive(doc)
    rules.check_can_edit(visit, station, doc, user.id, user.is_admin)
    request = await request_repo.require(ctx.db, visit["request_id"])
    return visit, station, doc, request


@router.post(ONE + "/media")
async def add_element_media(
    id: IdPath, station_id: IdPath, element_id: IdPath, body: ElementMediaIn, user: Worker,
    ctx: CtxDep,
) -> ElementOut:
    """A photo, a video or (on Config) any file, for a section of the element."""
    visit, station, doc, request = await _editable(ctx, id, station_id, element_id, user)
    section = rules.check_section(doc["kind"], body.section)
    if rules.has_media(doc, body.media_id):
        return _out(doc, visit, station, user)  # already there: a retry
    now = ctx.clock.now()
    caption = rules.check_caption(body.caption)
    captured_at = rules.check_captured_at(body.captured_at, now)
    facts = rules.check_file(
        await file_repo.file_facts(ctx.media, body.media_id, ctx.request_id), kind=doc["kind"],
        owner=rules.owner_ref(id, station_id, element_id, section), user_id=user.id,
    )
    entry = rules.media_entry(facts, media_id=body.media_id, caption=caption,
                              captured_at=captured_at, by=user.id, by_name=user.name, now=now)
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.add_media(ctx.db, element_id, section, entry, now=now, by=user.id,
                                       session=s)
        if updated is None:
            fresh = await _element(ctx, visit, station_id, element_id, s)
            rules.check_alive(fresh)
            holder["doc"] = fresh  # it just got there
            return
        current = await visit_repo.require(ctx.db, id, None, s)
        to_org, _ = rules.sharing_change(current, doc, updated)
        await _share(ctx, emitter, current, to_org, [], s)
        await emitter.element_media(updated, current, request, s, media_id=body.media_id,
                                    section=section, kind=facts.kind, change="added")
        holder["doc"] = updated

    await ctx.tx(save)
    return _out(holder["doc"], visit, station, user)


@router.patch(ONE + "/media/{media_id}")
async def change_element_media(
    id: IdPath, station_id: IdPath, element_id: IdPath, media_id: IdPath,
    body: ElementMediaPatch, user: Worker, ctx: CtxDep,
) -> ElementOut:
    """A caption, or hide a file from the client (W11-13) and show it again."""
    visit, station, doc, request = await _editable(ctx, id, station_id, element_id, user)
    section, entry = rules.find_media(doc, media_id)
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
        return _out(doc, visit, station, user)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.change_media(ctx.db, element_id, section, media_id, fields,
                                          now=now, by=user.id, session=s)
        if updated is None:
            fresh = await _element(ctx, visit, station_id, element_id, s)
            rules.check_alive(fresh)
            rules.find_media(fresh, media_id)  # gone: not found
            raise Conflict("This was just changed by someone else. Reload and try again",
                           code="element_changed")
        current = await visit_repo.require(ctx.db, id, None, s)
        to_org, to_staff = rules.sharing_change(current, doc, updated)
        await _share(ctx, emitter, current, to_org, to_staff, s)
        for change in changes:
            await emitter.element_media(updated, current, request, s, media_id=media_id,
                                        section=section, kind=entry["kind"], change=change)
        holder["doc"] = updated

    await ctx.tx(save)
    return _out(holder["doc"], visit, station, user)


@router.delete(ONE + "/media/{media_id}")
async def remove_element_media(
    id: IdPath, station_id: IdPath, element_id: IdPath, media_id: IdPath, user: Worker,
    ctx: CtxDep,
) -> ElementOut:
    """Take a file off the element and delete it."""
    visit, station, doc, request = await _editable(ctx, id, station_id, element_id, user)
    section, entry = rules.find_media(doc, media_id)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.remove_media(ctx.db, element_id, section, media_id, now=now,
                                          by=user.id, session=s)
        if updated is None:
            holder["doc"] = await _element(ctx, visit, station_id, element_id, s)
            return  # it was just removed by someone else: nothing left to do
        current = await visit_repo.require(ctx.db, id, None, s)
        await emitter.media_deletion([media_id], "removed_from_visit", current, request, s)
        await emitter.element_media(updated, current, request, s, media_id=media_id,
                                    section=section, kind=entry["kind"], change="removed")
        holder["doc"] = updated

    await ctx.tx(save)
    return _out(holder["doc"], visit, station, user)
