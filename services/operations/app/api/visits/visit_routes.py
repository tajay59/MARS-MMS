"""Visits (TRD §3.2 visits module; PRD VIS-1 to VIS-4, VIS-9, VIS-11; AFD J5 steps 3, 5 and 5b).

Phase 4 W10: schedule, list, read, reschedule, cancel, restore, start, arrive, depart, end. Every
change goes through `domain/visits/` and is written, with the request's derived status and the
events, in one transaction (rule 2, ADR-17). The lifecycle moves are idempotent: the same move by
the same person again returns the visit as it is (the offline sync of Phase 5 relies on that).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, Forbidden, ValidationFailed
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import Ctx, CtxDep
from app.api.visits import board_versions, glue
from app.api.visits.schemas import (
    AtIn,
    EndIn,
    StaffList,
    StaffOut,
    VisitCancelIn,
    VisitIn,
    VisitOut,
    VisitPage,
    VisitPatch,
)
from app.domain.requests import staffing
from app.domain.requests.state import Status
from app.domain.visits import elements as element_rules
from app.domain.visits import lifecycle, schedule
from app.domain.visits.state import VStatus
from app.events.publish import Emitter, ev
from app.repo.requests import requests as request_repo
from app.repo.stations import stations as station_repo
from app.repo.stations.common import stamp
from app.repo.visits import elements as element_repo
from app.repo.visits import visits as repo

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])

Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client their own org
StaffReader = Annotated[User, Depends(require_roles("technician", "admin", "viewer"))]
Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
Admin = Annotated[User, Depends(require_roles("admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]

AfterWrite = Callable[[AsyncClientSession, dict[str, Any], Emitter], Awaitable[None]]

# Visits can be planned while the request is being worked on, and not before or after
SCHEDULABLE = frozenset({Status.ASSIGNED, Status.SCHEDULED, Status.IN_PROGRESS})


async def boards(
    ctx: Ctx, docs: list[dict[str, Any]], viewer: User
) -> dict[str, dict[str, element_rules.Summary]]:
    """Each station's board at a glance, by visit and station. A client counts the shared
    elements of ended visits only (W11-28)."""
    found: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for element in await element_repo.for_visits(ctx.db, [d["_id"] for d in docs], viewer):
        found.setdefault(element["visit_id"], {}).setdefault(element["station_id"], []).append(
            element)
    out: dict[str, dict[str, element_rules.Summary]] = {}
    for doc in docs:
        mine = found.get(doc["_id"], {})
        if viewer.is_client and not element_rules.ended(doc):
            mine = {}
        out[doc["_id"]] = {
            s["station_id"]: element_rules.summarize(mine.get(s["station_id"], []))
            for s in doc["stations"]
        }
    return out


async def built(
    ctx: Ctx, doc: dict[str, Any], request: dict[str, Any] | None, viewer: User
) -> VisitOut:
    return VisitOut.build(doc, request, viewer, (await boards(ctx, [doc], viewer))[doc["_id"]])


async def _out(ctx: Ctx, doc: dict[str, Any], viewer: User) -> VisitOut:
    request = await request_repo.get(ctx.db, doc["request_id"])
    return await built(ctx, doc, request, viewer)


async def _people(ctx: Ctx, ids: list[str]) -> list[dict[str, str]]:
    """Everyone chosen exists and may attend (an active technician or admin), with their names."""
    people = staffing.check_assignable(ids, await ctx.staff.lookup(ids, ctx.request_id))
    return [{"id": p.id, "name": p.name} for p in people]


def _names_for(doc: dict[str, Any], extra: list[dict[str, str]]) -> list[dict[str, str]]:
    """The visit's staff in order, names kept for people already on it."""
    known = {p["id"]: p for p in [*doc.get("staff", []), *extra]}
    return [known[i] for i in doc["staff_ids"] if i in known]


# --- scheduling and reading ---------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def schedule_visit(
    body: VisitIn, user: Worker, ctx: CtxDep, response: Response
) -> VisitOut:
    """VIS-1: the request's assigned staff or an admin plan a visit: dates, who attends (one the
    lead), which of the request's stations, and who owns each. The request becomes Scheduled.
    Sending the same `id` again returns the visit that was made (200)."""
    existing = await repo.get(ctx.db, body.id) if body.id else None
    if existing is not None:
        if existing["created_by"] != user.id:
            raise Conflict("That ID is already used", code="id_taken")
        response.status_code = status.HTTP_200_OK
        return await _out(ctx, existing, user)

    request = await request_repo.require(ctx.db, body.request_id)
    if Status(request["status"]) not in SCHEDULABLE:
        raise Conflict("A visit can be planned once the request is assigned",
                       code="request_not_schedulable")
    if not schedule.can_schedule(user.id, user.is_admin, request.get("assigned_staff_ids", [])):
        raise Forbidden("Only the people on this request can plan a visit", code="not_assigned")
    schedule.check_window(body.planned_start, body.planned_end)
    staff_ids, lead = schedule.clean_staff(body.staff_ids, body.lead_staff_id)
    owners = schedule.clean_owners(
        [(s.station_id, s.owner_staff_id) for s in body.stations], staff_ids, lead,
        request["station_ids"],
    )
    staff = await _people(ctx, staff_ids)
    details = await station_repo.by_ids(ctx.db, list(owners))
    notes = schedule.clean_notes(body.notes)
    visit_id = body.id or new_id()
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        locked = await glue.lock_request(ctx, request["_id"], s)
        if Status(locked["status"]) not in SCHEDULABLE:
            raise Conflict("A visit can be planned once the request is assigned",
                           code="request_not_schedulable")
        schedule.check_stations_free(list(owners), await repo.live_for_request(
            ctx.db, request["_id"], s))
        ref = await repo.next_ref(ctx.db, locked["ref"], s)
        doc = stamp({
            "_id": visit_id, "ref": ref, "request_id": request["_id"], "org_id": locked["org_id"],
            "staff_ids": staff_ids, "staff": staff, "lead_staff_id": lead,
            "planned_start": body.planned_start, "planned_end": body.planned_end,
            "notes": notes, "status": VStatus.PLANNED.value, "locked": False,
            "report_status": "none", "report_version": None, "prepared_on": [],
            "started_at": None, "ended_at": None, "additional_visit_required": None,
            "follow_up_notes": None, "cancelled_at": None, "cancel_reason": None,
            "stations": [
                schedule.new_station(sid, owner, details.get(sid, {}))
                for sid, owner in owners.items()
            ],
        }, now, user.id)
        await repo.insert(ctx.db, doc, s)
        await emitter.visit(ev.VisitScheduled, "visit.scheduled", doc, locked, s)
        holder["request"] = await glue.settle(ctx, user, locked, s, note=f"Visit {ref} planned")
        holder["doc"] = doc

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        # The same `id` arrived twice at once: the other one won. Hand back what it made.
        won = await repo.get(ctx.db, visit_id)
        if won is None or won["created_by"] != user.id:
            raise Conflict("That ID is already used", code="id_taken") from None
        response.status_code = status.HTTP_200_OK
        return await _out(ctx, won, user)
    return await built(ctx, holder["doc"], holder["request"], user)


@router.get("/mine")
async def my_visits(user: StaffReader, ctx: CtxDep) -> VisitPage:
    """The visits I attend that are planned or under way, soonest first (AFD "My upcoming
    visits")."""
    docs = await repo.mine(ctx.db, user)
    requests = await glue.requests_by_id(ctx, [d["request_id"] for d in docs])
    summaries = await boards(ctx, docs, user)
    return VisitPage(
        items=[VisitOut.build(d, requests.get(d["request_id"]), user, summaries[d["_id"]])
               for d in docs],
        total=len(docs), next_after=None,
    )


@router.get("/staff")
async def attending_staff(user: Worker, ctx: CtxDep) -> StaffList:
    """The active technicians and admins to pick from when scheduling (VIS-1). Operations keeps
    no copy of users (rule 1): auth answers, and only names and roles come back. Admins can list
    users in auth; a technician who is assigned to the request cannot, so the list is here."""
    people = await ctx.staff.staff(ctx.request_id)
    return StaffList(items=[
        StaffOut(id=p["id"], name=p["name"], roles=sorted(p["roles"])) for p in people
    ])


@router.get("")
async def list_visits(
    viewer: Reader,
    ctx: CtxDep,
    request_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    staff_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    start_from: Annotated[datetime | None, Query(alias="from")] = None,
    start_to: Annotated[datetime | None, Query(alias="to")] = None,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> VisitPage:
    """Soonest first. A client sees their organization's visits (VIS-11)."""
    statuses = tuple(status_ or ())
    if any(s not in {v.value for v in VStatus} for s in statuses):
        raise ValidationFailed("Unknown status", code="bad_status", field="status")
    docs, total = await repo.search(
        ctx.db, viewer, request_id=request_id, staff_id=staff_id, statuses=statuses,
        start_from=start_from, start_to=start_to, after=after, limit=limit + 1,
    )
    more = len(docs) > limit
    docs = docs[:limit]
    requests = await glue.requests_by_id(ctx, [d["request_id"] for d in docs])
    summaries = await boards(ctx, docs, viewer)
    return VisitPage(
        items=[VisitOut.build(d, requests.get(d["request_id"]), viewer, summaries[d["_id"]])
               for d in docs],
        total=total, next_after=docs[-1]["_id"] if more and docs else None,
    )


@router.get("/{id}")
async def get_visit(id: IdPath, viewer: Reader, ctx: CtxDep) -> VisitOut:
    """A client reads their organization's visits only; another's is not found (rule 4)."""
    return await _out(ctx, await repo.require(ctx.db, id, viewer), viewer)


# --- changing a visit ---------------------------------------------------------------------------


async def _assigned(ctx: Ctx, visit: dict[str, Any]) -> list[str]:
    request = await request_repo.require(ctx.db, visit["request_id"])
    return list(request.get("assigned_staff_ids", []))


async def _write(
    ctx: Ctx, user: User, visit: dict[str, Any], fields: dict[str, Any], *,
    emit: list[tuple[Any, str, dict[str, Any]]], settle_note: str | None,
    expected_version: int | None = None, after: AfterWrite | None = None,
) -> VisitOut:
    """One change: the visit, its events and (when its status moved) the request's status, in one
    transaction. `emit` is `(model, type, extra)` for each event, written in that order. `after`
    runs once the visit is written and before its events: ending a visit shares the board's
    files there, so a failure undoes everything."""
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        locked = await glue.lock_request(ctx, visit["request_id"], s)
        updated = await repo.update(
            ctx.db, visit["_id"], fields, now=now, by=user.id, session=s,
            expected_status=visit["status"], expected_version=expected_version,
        )
        if after is not None:
            await after(s, updated, emitter)
        for model, type_, extra in emit:
            await emitter.visit(model, type_, updated, locked, s, before=visit, **extra)
        holder["request"] = (
            await glue.settle(ctx, user, locked, s, note=settle_note) if settle_note else locked
        )
        holder["doc"] = updated

    await ctx.tx(save)
    return await built(ctx, holder["doc"], holder["request"], user)


@router.patch("/{id}")
async def change_visit(id: IdPath, body: VisitPatch, user: Worker, ctx: CtxDep) -> VisitOut:
    """VIS-2, AFD J5 steps 5 and 5b. A planned visit: dates, people, lead, stations, owners and
    notes. A started visit: only who owns which station, by the lead or an admin."""
    visit = await repo.require(ctx.db, id)
    request = await request_repo.require(ctx.db, visit["request_id"])
    status_ = VStatus(visit["status"])
    sent = body.model_fields_set - {"version"}
    if status_ is VStatus.CANCELLED:
        raise Conflict("This visit was cancelled", code="visit_cancelled")
    if status_ is VStatus.ENDED:
        raise Conflict("This visit has already ended", code="already_ended")

    emit: list[tuple[Any, str, dict[str, Any]]] = []
    if status_ is VStatus.STARTED:
        if sent - {"stations"}:
            raise Conflict("Once a visit has started only its station owners can change",
                           code="visit_started")
        wanted: dict[str, str] = {}
        for item in body.stations or []:
            if item.owner_staff_id is None:
                raise ValidationFailed("Say who owns the station", code="owner_required",
                                       field="stations", station_id=item.station_id)
            wanted[item.station_id] = item.owner_staff_id
        changes = schedule.change_owners(visit, wanted, user.id, user.is_admin)
    else:
        schedule.require_manage(user.id, user.is_admin, visit,
                                request.get("assigned_staff_ids", []))
        edit = schedule.Edit(
            planned_start=body.planned_start, planned_end=body.planned_end,
            staff_ids=body.staff_ids, lead_staff_id=body.lead_staff_id,
            stations=[(s.station_id, s.owner_staff_id) for s in body.stations]
            if body.stations is not None else None,
            notes=body.notes, notes_given="notes" in sent,
        )
        wanted_stations = [s.station_id for s in body.stations] if body.stations else []
        details = await station_repo.by_ids(ctx.db, wanted_stations) if wanted_stations else {}
        others = await repo.live_for_request(ctx.db, visit["request_id"], excluding=visit["_id"])
        extra_staff = await _people(ctx, body.staff_ids) if body.staff_ids is not None else []
        changes = schedule.edit_planned(visit, edit, request["station_ids"], others, details)
        if "staff_ids" in changes.fields:
            changes.fields["staff"] = _names_for({**visit, **changes.fields}, extra_staff)
    if not changes.fields:
        return await _out(ctx, visit, user)

    plan_changed = [c for c in changes.changed if c in ("dates", "staff", "lead", "stations")]
    if plan_changed:
        emit.append((ev.VisitRescheduled, "visit.rescheduled", {"changed_fields": changes.changed}))
    named = {s["station_id"]: s for s in visit["stations"]}
    emit += [
        (ev.VisitStationOwnerChanged, "visit.station_owner_changed",
         {"station_id": sid, "from_staff_id": old, "to_staff_id": new,
          "station_code": named.get(sid, {}).get("station_code"),
          "station_name": named.get(sid, {}).get("station_name")})
        for sid, old, new in changes.owner_changes
    ]
    return await _write(ctx, user, visit, changes.fields, emit=emit, settle_note=None,
                        expected_version=body.version)


@router.post("/{id}/cancel")
async def cancel_visit(id: IdPath, body: VisitCancelIn, user: Worker, ctx: CtxDep) -> VisitOut:
    """VIS-2: a planned visit is cancelled; the request returns to Assigned when no other visit
    is planned."""
    visit = await repo.require(ctx.db, id)
    schedule.require_manage(user.id, user.is_admin, visit, await _assigned(ctx, visit))
    reason = body.reason or None
    result = lifecycle.cancel(visit, reason, ctx.clock.now())
    if result.noop:
        return await _out(ctx, visit, user)
    return await _write(
        ctx, user, visit, result.fields,
        emit=[(ev.VisitCancelled, "visit.cancelled", {"reason": reason})],
        settle_note=f"Visit {visit['ref']} cancelled",
    )


@router.post("/{id}/restore")
async def restore_visit(id: IdPath, user: Admin, ctx: CtxDep) -> VisitOut:
    """An admin brings a cancelled visit back: work was recorded on it offline (TRD §7.4)."""
    visit = await repo.require(ctx.db, id)
    result = lifecycle.restore(visit)
    if result.noop:
        return await _out(ctx, visit, user)
    schedule.check_stations_free(
        [s["station_id"] for s in visit["stations"]],
        await repo.live_for_request(ctx.db, visit["request_id"], excluding=visit["_id"]),
    )
    return await _write(
        ctx, user, visit, result.fields,
        emit=[(ev.VisitRestored, "visit.restored", {})],
        settle_note=f"Visit {visit['ref']} restored",
    )


@router.post("/{id}/start")
async def start_visit(id: IdPath, body: AtIn, user: Worker, ctx: CtxDep) -> VisitOut:
    """VIS-4: attending staff start the visit; the request is In progress."""
    visit = await repo.require(ctx.db, id)
    now = ctx.clock.now()
    result = lifecycle.start(visit, user.id, user.is_admin, body.at, now)
    if result.noop:
        return await _out(ctx, visit, user)
    return await _write(
        ctx, user, visit, result.fields,
        emit=[(ev.VisitStarted, "visit.started", {"started_at": result.fields["started_at"]})],
        settle_note=f"Visit {visit['ref']} started",
    )


async def _station_move(
    ctx: Ctx, user: User, visit: dict[str, Any], station_id: str, field: str, at: Any,
    model: Any, type_: str,
) -> VisitOut:
    """Arrival or departure: one station's field is set, the others are left as they are."""
    now = ctx.clock.now()
    fn = lifecycle.arrive if field == "arrived_at" else lifecycle.depart
    result = fn(visit, station_id, user.id, user.is_admin, at, now)
    if result.noop:
        return await _out(ctx, visit, user)
    when = next(s[field] for s in result.fields["stations"] if s["station_id"] == station_id)
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        request = await request_repo.require(ctx.db, visit["request_id"], None, s)
        updated = await repo.set_station(ctx.db, visit["_id"], station_id, {field: when},
                                         now=now, by=user.id, session=s)
        await emitter.visit(model, type_, updated, request, s, before=visit,
                            station_id=station_id, at=when)
        holder["doc"], holder["request"] = updated, request

    await ctx.tx(save)
    return await built(ctx, holder["doc"], holder["request"], user)


@router.post("/{id}/stations/{station_id}/arrive")
async def arrive(
    id: IdPath, station_id: IdPath, body: AtIn, user: Worker, ctx: CtxDep
) -> VisitOut:
    """VIS-4: the station's owner records arriving there."""
    visit = await repo.require(ctx.db, id)
    return await _station_move(ctx, user, visit, station_id, "arrived_at", body.at,
                               ev.VisitStationArrived, "visit.station_arrived")


@router.post("/{id}/stations/{station_id}/depart")
async def depart(
    id: IdPath, station_id: IdPath, body: AtIn, user: Worker, ctx: CtxDep
) -> VisitOut:
    """VIS-4: the station's owner records leaving it (after arriving)."""
    visit = await repo.require(ctx.db, id)
    return await _station_move(ctx, user, visit, station_id, "departed_at", body.at,
                               ev.VisitStationDeparted, "visit.station_departed")


@router.post("/{id}/end")
async def end_visit(id: IdPath, body: EndIn, user: Worker, ctx: CtxDep) -> VisitOut:
    """VIS-9: end the visit and say whether another is needed. If so the request goes back to
    Assigned to be scheduled again; if not it waits for the visit report (Phase 6). Incomplete
    tasks are only a warning in the End dialog: an end synced from a phone can't answer a
    question, so the server never refuses it for them (W11-33)."""
    visit = await repo.require(ctx.db, id)
    now = ctx.clock.now()
    result = lifecycle.end(
        visit, user.id, user.is_admin, additional_visit_required=body.additional_visit_required,
        follow_up_notes=body.follow_up_notes, at=body.at, now=now,
    )
    if result.noop:
        return await _out(ctx, visit, user)
    # Config elements whose After files are not yet a version: their files are checked with
    # media first (a network call), and one still being checked refuses the end (W11-24)
    due = [e for e in await element_repo.for_visits(ctx.db, [visit["_id"]])
           if element_rules.config_version_due(e)]
    versions = [(e, await board_versions.checked_files(ctx, e), new_id()) for e in due]

    async def share(s: AsyncClientSession, ended: dict[str, Any], emitter: Emitter) -> None:
        for element, checked, version_id in versions:
            await board_versions.make_version(ctx, user, ended, element, checked, version_id, s,
                                              emitter)
        # The client sees the shared elements' files from now on, except what was hidden
        # (W11-28). The same transaction as the end, so a visit is never ended and unshared.
        board = await element_repo.for_visits(ctx.db, [ended["_id"]], None, s)
        shown = sorted({m for e in board if e.get("shared") for m in
                        element_rules.shown_media_ids(e)})
        if shown:
            seq = await repo.next_visibility_seq(ctx.db, ended["_id"], s)
            await emitter.visit_visibility(shown, "org", ended, s, version=seq)

    return await _write(
        ctx, user, visit, result.fields, after=share,
        emit=[(ev.VisitEnded, "visit.ended", {
            "ended_at": result.fields["ended_at"],
            "additional_visit_required": body.additional_visit_required,
            "follow_up_notes": result.fields["follow_up_notes"],
            "config_version_ids": [version_id for _, _, version_id in versions],
        })],
        settle_note=f"Visit {visit['ref']} ended",
    )
