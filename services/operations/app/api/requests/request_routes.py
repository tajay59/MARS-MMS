"""Maintenance requests (TRD §3.2 requests module; PRD REQ-1, REQ-2, REQ-4 to REQ-6, REQ-8,
REQ-11, REQ-15, REQ-16; AFD J3, J4).

Phase 3 W8: create, list, read, edit, approve, deny and cancel. W9: assign, claim and release
(the queue is `queue_routes.py`, comments follow); the statuses from Scheduled on come from
visits (Phase 4). Every status change goes through `domain/requests/state.py` and writes its
events in the same transaction as the change (rule 2).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, Forbidden, ValidationFailed, VersionConflict
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import Ctx, CtxDep
from app.api.requests.attach import verified
from app.api.requests.schemas import (
    Action as ActionName,
)
from app.api.requests.schemas import (
    AssignIn,
    CancelIn,
    DenyIn,
    RequestDetail,
    RequestIn,
    RequestPage,
    RequestPatch,
    RequestSummary,
    Workload,
)
from app.domain.requests import comments as comment_rules
from app.domain.requests import rules, staffing
from app.domain.requests.state import MILESTONES, Action, Status, Who, allowed, transition
from app.events.publish import ev
from app.repo.requests import comments as comment_repo
from app.repo.requests import requests as repo
from app.repo.stations import orgs
from app.repo.stations import stations as station_repo
from app.repo.stations.common import Db, stamp

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])

Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client their own org
Creator = Annotated[User, Depends(require_roles("client", "admin"))]
Admin = Annotated[User, Depends(require_roles("admin"))]
Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
# The table actions with a button of their own. Assign, claim and release are worked out by
# `staffing.actions_for` (who is on the request matters); the client's accept and reject wait
# for Phase 6.
OFFERED = frozenset({Action.APPROVE, Action.DENY, Action.CANCEL})


def who_of(user: User) -> Who | None:
    """The role that decides what a person may do to a request. Viewers have none."""
    if user.is_admin:
        return Who.ADMIN
    if user.is_client:
        return Who.CLIENT
    if "technician" in user.roles:
        return Who.TECHNICIAN
    return None


def require_who(user: User) -> Who:
    who = who_of(user)
    if who is None:
        raise Forbidden()  # a viewer never changes a request (rule 5)
    return who


async def _names(db: Db, docs: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]],
                                                             dict[str, str]]:
    """The stations and organization names a page of requests shows, fetched together."""
    stations = await station_repo.by_ids(
        db, sorted({i for d in docs for i in d["station_ids"]})
    )
    org_names: dict[str, str] = {}
    for org_id in {d["org_id"] for d in docs}:
        org = await orgs.get(db, org_id)
        if org is not None:
            org_names[org_id] = org["name"]
    return stations, org_names


async def _detail(ctx: Ctx, doc: dict[str, Any], user: User) -> RequestDetail:
    stations, org_names = await _names(ctx.db, [doc])
    who = who_of(user)
    actions: list[str] = []
    if who is not None:
        actions = [a.value for a in allowed(Status(doc["status"]), who) if a in OFFERED]
        actions += staffing.actions_for(
            Status(doc["status"]), who, user.id, doc.get("assigned_staff_ids", [])
        )
        try:  # editing follows its own rule (REQ-11)
            rules.check_can_edit(Status(doc["status"]), who)
            actions.append("edit")
        except (ValidationFailed, Forbidden):
            pass
    seen = await comment_repo.counts(ctx.db, [doc["_id"]], user)
    return RequestDetail.build(doc, stations, org_names, cast(list[ActionName], actions),
                               comment_count=seen.get(doc["_id"], 0))


def _entry(
    *, from_status: str | None, to: Status, user: User, now: datetime, event_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "from": from_status, "to": to.value, "by": user.id, "by_name": user.name, "at": now,
        "note": note, "event_id": event_id,
    }


@router.get("")
async def list_requests(
    viewer: Reader,
    ctx: CtxDep,
    status_: Annotated[list[str] | None, Query(alias="status")] = None,
    org_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    country: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
    station_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    category: Annotated[str | None, Query(max_length=32)] = None,
    priority: Annotated[str | None, Query(max_length=16)] = None,
    assigned_to: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RequestPage:
    """REQ-8, REQ-15: newest first. A client sees their organization's requests only; the
    date range is inclusive of both days."""
    statuses = tuple(dict.fromkeys(status_ or ()))
    if bad := [s for s in statuses if s not in {x.value for x in Status}]:
        raise ValidationFailed(f"Unknown status: {bad[0]}", code="bad_status", field="status")
    station_ids: tuple[str, ...] | None = None
    if country or station_id:
        station_ids = tuple(await station_repo.ids_where(
            ctx.db, country=country, station_id=station_id
        ))
    f = repo.Filters(
        statuses=statuses, org_id=org_id, station_ids=station_ids, category=category,
        priority=priority, assigned_to=assigned_to if not viewer.is_client else None,
        created_from=datetime.combine(from_, time.min, UTC) if from_ else None,
        created_to=datetime.combine(to + timedelta(days=1), time.min, UTC) if to else None,
        q=q.strip() if q and q.strip() else None,
    )
    found, total = await repo.search(ctx.db, viewer, f, after=after, limit=limit + 1)
    more = len(found) > limit
    found = found[:limit]
    stations, org_names = await _names(ctx.db, found)
    return RequestPage(
        items=[RequestSummary.of(d, stations, org_names) for d in found], total=total,
        next_after=found[-1]["_id"] if more else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_request(
    body: RequestIn, user: Creator, ctx: CtxDep, response: Response
) -> RequestDetail:
    """REQ-1, REQ-2, REQ-4. A client's request starts Submitted; an admin's, made for an
    organization, starts Approved. Sending the same `id` again returns the request that
    was made (200), so a retry on a poor connection can't make a second one."""
    existing = await repo.get(ctx.db, body.id) if body.id else None
    if existing is not None:
        if existing["created_by"] != user.id:
            raise Conflict("That ID is already used", code="id_taken")
        response.status_code = status.HTTP_200_OK
        return await _detail(ctx, existing, user)

    if user.is_admin:
        if body.org_id is None:
            raise ValidationFailed("Choose the organization", code="required", field="org_id")
        org_id = body.org_id
        org = await orgs.get(ctx.db, org_id)
        if org is None or org["status"] != "active":
            raise ValidationFailed("Choose an active organization", code="org_inactive",
                                   field="org_id")
    else:
        if body.org_id is not None and body.org_id != user.org_id:
            raise ValidationFailed("A request is made for your own organization",
                                   code="wrong_org", field="org_id")
        if user.org_id is None:
            raise Forbidden()
        org_id = user.org_id

    title = rules.clean_text(body.title, "title", maximum=rules.MAX_TITLE)
    description = rules.clean_text(body.description, "description", maximum=rules.MAX_DESCRIPTION)
    station_ids = rules.clean_stations(body.station_ids)
    # A client's reads are scoped to their organization: a station that is not theirs is
    # simply not found, and so reads the same as one that does not exist
    found = [await station_repo.get(ctx.db, i, user) for i in station_ids]
    rules.check_stations_belong(org_id, found, station_ids)

    media_ids = comment_rules.check_media_ids(body.media_ids)
    if media_ids and not body.id:
        raise ValidationFailed("Files need the request's ID", code="id_required", field="id")
    request_id = body.id or new_id()
    attachments = await verified(ctx, user, comment_rules.request_owner_ref(request_id),
                                 media_ids)
    now = ctx.clock.now()
    to = Status.APPROVED if user.is_admin else Status.SUBMITTED
    event_id = new_id()
    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        ref = await repo.next_ref(ctx.db, now, s)
        milestones = {MILESTONES[Status.SUBMITTED]: now}
        if to is Status.APPROVED:
            milestones[MILESTONES[Status.APPROVED]] = now
        doc = stamp({
            "_id": request_id, "ref": ref, "org_id": org_id, "station_ids": station_ids,
            "title": title, "description": description, "category": body.category,
            "priority": body.priority, "status": to.value,
            "status_history": [_entry(from_status=None, to=to, user=user, now=now,
                                      event_id=event_id)],
            "assigned_staff_ids": [], "assigned_staff": [], "denial_reason": None,
            "cancel_reason": None, "rework_since": None, "review_started_at": None,
            "reminders_sent": [], "client_verification": None, "reopen_count": 0,
            "attachments": attachments, "milestones": milestones, "requester_name": user.name,
        }, now, user.id)
        await repo.insert(ctx.db, doc, s)
        await emitter.request(ev.RequestSubmitted, "request.submitted", doc, s,
                              by_admin=user.is_admin)
        await emitter.request_status(doc, s, from_status=None, event_id=event_id)
        if attachments:
            await emitter.attachments_visibility("request", doc, doc, media_ids, "org", s)
        holder["doc"] = doc

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        # The same `id` arrived twice at once: the other one won. Hand back what it made.
        won = await repo.get(ctx.db, request_id)
        if won is None or won["created_by"] != user.id:
            raise Conflict("That ID is already used", code="id_taken") from None
        response.status_code = status.HTTP_200_OK
        return await _detail(ctx, won, user)
    return await _detail(ctx, holder["doc"], user)


@router.get("/workload")
async def get_workload(_: Admin, ctx: CtxDep) -> Workload:
    """How many open requests each person has, for the Assign dialog (W9)."""
    return Workload(open_requests=await repo.workload(ctx.db))


@router.get("/{id}")
async def get_request(id: IdPath, viewer: Reader, ctx: CtxDep) -> RequestDetail:
    """REQ-8: the request with its status history. A client sees their organization's only."""
    return await _detail(ctx, await repo.require(ctx.db, id, viewer), viewer)


@router.patch("/{id}")
async def patch_request(
    id: IdPath, body: RequestPatch, user: Creator, ctx: CtxDep
) -> RequestDetail:
    """REQ-11: a client edits their own request while it is Submitted, Approved or Assigned;
    an admin until it is done. Only what is sent changes."""
    current = await repo.require(ctx.db, id, user)
    who = require_who(user)
    rules.check_can_edit(Status(current["status"]), who)
    wanted: dict[str, Any] = {}
    for field in body.model_fields_set - {"version"}:
        value = getattr(body, field)
        if value is None:
            raise ValidationFailed("This can't be empty", code="required", field=field)
        if field == "title":
            value = rules.clean_text(value, "title", maximum=rules.MAX_TITLE)
        elif field == "description":
            value = rules.clean_text(value, "description", maximum=rules.MAX_DESCRIPTION)
        elif field == "station_ids":
            value = rules.clean_stations(value)
            found = [await station_repo.get(ctx.db, i, user) for i in value]
            rules.check_stations_belong(current["org_id"], found, value)
        wanted[field] = value
    changed = rules.changed_fields(current, {**current, **wanted})
    if not changed:
        if body.version != current["version"]:
            raise VersionConflict()
        return await _detail(ctx, current, user)
    changes = {f: wanted[f] for f in changed}
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await repo.update(
            ctx.db, id, changes, now=now, by=user.id, session=s,
            expected_version=body.version,
        )
        await emitter.request(ev.RequestUpdated, "request.updated", updated, s,
                              before=current, changed_fields=changed)
        return updated

    return await _detail(ctx, await ctx.tx(save), user)


async def _move(
    ctx: Ctx, user: User, current: dict[str, Any], action: Action, *,
    reason: str | None, changes: dict[str, Any], event: tuple[Any, str, dict[str, Any]],
) -> RequestDetail:
    """One status change: the state machine decides, then the record, its history and both
    events are written together. `event` is the specific one (`request.approved`, ...)."""
    who = require_who(user)
    before = Status(current["status"])
    to = transition(before, action, who, reason=reason)
    now = ctx.clock.now()
    event_id = new_id()
    emitter = ctx.emitter(user)
    milestones = dict(current.get("milestones", {}))
    if (key := MILESTONES.get(to)) and key not in milestones:
        milestones[key] = now
    set_ = {"status": to.value, "milestones": milestones, **changes}
    model, type_, extra = event

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await repo.update(
            ctx.db, current["_id"], set_, now=now, by=user.id, session=s,
            expected_status=before.value,
            history=_entry(from_status=before.value, to=to, user=user, now=now,
                           event_id=event_id, note=reason),
        )
        await emitter.request(model, type_, updated, s, before=current, **extra)
        await emitter.request_status(updated, s, from_status=before.value, event_id=event_id,
                                     reason=reason)
        return updated

    return await _detail(ctx, await ctx.tx(save), user)


@router.post("/{id}/approve")
async def approve_request(id: IdPath, user: Admin, ctx: CtxDep) -> RequestDetail:
    """REQ-6: Submitted to Approved. The request then joins the queue."""
    current = await repo.require(ctx.db, id)
    return await _move(ctx, user, current, Action.APPROVE, reason=None, changes={},
                       event=(ev.RequestApproved, "request.approved", {}))


@router.post("/{id}/deny")
async def deny_request(id: IdPath, body: DenyIn, user: Admin, ctx: CtxDep) -> RequestDetail:
    """REQ-6: Submitted to Denied. The reason is required and the client sees it."""
    current = await repo.require(ctx.db, id)
    return await _move(
        ctx, user, current, Action.DENY, reason=body.reason,
        changes={"denial_reason": body.reason.strip()},
        event=(ev.RequestDenied, "request.denied", {"reason": body.reason.strip()}),
    )


@router.post("/{id}/cancel")
async def cancel_request(
    id: IdPath, body: CancelIn, user: Creator, ctx: CtxDep
) -> RequestDetail:
    """REQ-11: a client cancels their own request up to Assigned; an admin any time before it
    is done, with a reason from Scheduled on. Planned visits are cancelled in the same
    transaction once visits exist (Phase 4)."""
    current = await repo.require(ctx.db, id, user)
    reason = body.reason.strip() if body.reason else None
    return await _move(
        ctx, user, current, Action.CANCEL, reason=reason,
        changes={"cancel_reason": reason},
        event=(ev.RequestCancelled, "request.cancelled",
               {"reason": reason, "cancelled_by": "admin" if user.is_admin else "client"}),
    )


def _people(doc: dict[str, Any]) -> list[staffing.Person]:
    return [staffing.Person(i, n) for i, n in doc.get("assigned_staff", [])]


async def _apply_staff(
    ctx: Ctx, user: User, current: dict[str, Any], change: staffing.StaffChange, *,
    claimed: bool = False, expected_version: int | None = None,
) -> RequestDetail:
    """Write who is on the request. A move between statuses also writes its history entry and
    `request.status_changed`; a change among staff alone writes `request.staff_changed`."""
    now = ctx.clock.now()
    before = Status(current["status"])
    emitter = ctx.emitter(user)
    names = [p.name for p in change.staff]
    set_: dict[str, Any] = {
        "assigned_staff_ids": [p.id for p in change.staff],
        "assigned_staff": [[p.id, p.name] for p in change.staff],
    }
    history: dict[str, Any] | None = None
    event_id = new_id()
    if change.to is not None:
        milestones = dict(current.get("milestones", {}))
        if change.to is Status.ASSIGNED:
            milestones["assigned_at"] = now
        else:  # released: the clock for assignment starts again
            milestones.pop("assigned_at", None)
        set_.update(status=change.to.value, milestones=milestones)
        gone = [p.name for p in _people(current) if p.id in change.removed]
        note = (
            f"Claimed by {user.name}" if claimed
            else f"Assigned to {', '.join(names)}" if change.action is Action.ASSIGN
            else f"Released by {user.name}" if gone == [user.name]
            else f"Unassigned by {user.name}"
        )
        history = _entry(from_status=before.value, to=change.to, user=user, now=now,
                         event_id=event_id, note=note)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await repo.update(
            ctx.db, current["_id"], set_, now=now, by=user.id, session=s,
            expected_status=before.value, expected_version=expected_version, history=history,
        )
        if change.action is Action.ASSIGN:
            await emitter.request(
                ev.RequestAssigned, "request.assigned", updated, s, before=current,
                staff_ids=[p.id for p in change.staff], staff_names=names, claimed=claimed,
                by_id=user.id,
            )
        elif change.action is Action.RELEASE:
            released = [p for p in _people(current) if p.id in change.removed]
            await emitter.request(
                ev.RequestReleased, "request.released", updated, s, before=current,
                released_ids=[p.id for p in released], released_names=[p.name for p in released],
                by_id=user.id,
            )
        else:
            await emitter.request(
                ev.RequestStaffChanged, "request.staff_changed", updated, s, before=current,
                staff_ids=[p.id for p in change.staff], staff_names=names,
                added=list(change.added), removed=list(change.removed),
            )
        if change.to is not None:
            await emitter.request_status(updated, s, from_status=before.value,
                                         event_id=event_id)
        return updated

    return await _detail(ctx, await ctx.tx(save), user)


@router.post("/{id}/assign")
async def assign_request(
    id: IdPath, body: AssignIn, user: Admin, ctx: CtxDep
) -> RequestDetail:
    """REQ-7: an admin puts one or more staff on an approved request (it becomes Assigned) or
    changes the staff of one that is Assigned. Visits decide from Scheduled on."""
    current = await repo.require(ctx.db, id)
    ids = staffing.clean_staff_ids(body.staff_ids)
    wanted = staffing.check_assignable(ids, await ctx.staff.lookup(ids, ctx.request_id))
    change = staffing.assign(Status(current["status"]), require_who(user), _people(current),
                             wanted)
    return await _apply_staff(ctx, user, current, change, expected_version=body.version)


@router.post("/{id}/claim")
async def claim_request(id: IdPath, user: Worker, ctx: CtxDep) -> RequestDetail:
    """REQ-7: a technician (or an admin) takes an approved request from the queue. Two people
    claiming at once: one wins, the other is told who."""
    current = await repo.require(ctx.db, id)
    me = staffing.Person(user.id, user.name)
    change = staffing.claim(Status(current["status"]), require_who(user), me, _people(current))
    try:
        return await _apply_staff(ctx, user, current, change, claimed=True)
    except Conflict as lost:
        fresh = await repo.get(ctx.db, id)
        if lost.extra.get("code") == "request_changed" and fresh and fresh.get("assigned_staff"):
            raise Conflict(
                "Someone else has claimed this request", code="already_assigned",
                claimed_by=[n for _, n in fresh["assigned_staff"]],
            ) from lost
        raise


@router.post("/{id}/release")
async def release_request(id: IdPath, user: Worker, ctx: CtxDep) -> RequestDetail:
    """A technician lets go of their claim, or an admin unassigns everyone. With nobody left
    the request returns to the queue (Assigned to Approved)."""
    current = await repo.require(ctx.db, id)
    me = staffing.Person(user.id, user.name)
    change = staffing.release(Status(current["status"]), require_who(user), me, _people(current))
    return await _apply_staff(ctx, user, current, change)
