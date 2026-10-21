"""What every visit change does to its request, in the change's own transaction (ADR-17, W10-6).

A route that changes a visit (a) takes the request's lock, (b) writes the visit and its event,
(c) calls `settle`, which reads all the request's visits, derives the status and writes it with
its history entry and `request.status_changed`. All of it is one Mongo transaction (rule 2), so
the request, its visits and the outbox never disagree.
"""

from __future__ import annotations

from typing import Any

from mms_common.auth import User
from mms_common.errors import NotFound
from mms_common.ids import new_id
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx
from app.domain.requests.recompute import recompute
from app.domain.requests.state import Status
from app.domain.visits import lifecycle
from app.domain.visits.state import VStatus
from app.events.publish import ev
from app.repo.requests import requests as request_repo
from app.repo.visits import visits as visit_repo


async def lock_request(ctx: Ctx, request_id: str, s: AsyncClientSession) -> dict[str, Any]:
    """Take the request, and make two visit changes on it queue up.

    The write moves `visit_seq`, not `version` (a request editor's stale-write check must not
    trip over a visit being planned). A second transaction touching the same request waits or
    retries here, so it derives the status from visits that include the first one's change.
    """
    doc: dict[str, Any] | None = await request_repo.col(ctx.db).find_one_and_update(
        {"_id": request_id}, {"$inc": {"visit_seq": 1}},
        return_document=ReturnDocument.AFTER, session=s,
    )
    if doc is None:
        raise NotFound()
    return doc


def history_entry(
    *, from_status: str, to: Status, user: User, now: Any, event_id: str, note: str
) -> dict[str, Any]:
    return {
        "from": from_status, "to": to.value, "by": user.id, "by_name": user.name, "at": now,
        "note": note, "event_id": event_id,
    }


async def settle(
    ctx: Ctx, user: User, request: dict[str, Any], s: AsyncClientSession, *, note: str
) -> dict[str, Any]:
    """Derive the request's status from its visits (read inside the transaction) and write it
    when it moved, with the first visit's start as a milestone. Returns the request as it is."""
    visits = await visit_repo.for_request(ctx.db, request["_id"], None, s)
    settled = recompute(request, visits)
    now = ctx.clock.now()
    milestones = dict(request.get("milestones", {}))
    changes: dict[str, Any] = {}
    if settled.first_visit_at is not None and "first_visit_at" not in milestones:
        milestones["first_visit_at"] = settled.first_visit_at
        changes["milestones"] = milestones
    before = request["status"]
    if settled.status.value != before:
        changes["status"] = settled.status.value
        changes["milestones"] = milestones
    if not changes:
        return request
    event_id = new_id()
    history = (
        history_entry(from_status=before, to=settled.status, user=user, now=now,
                      event_id=event_id, note=note)
        if "status" in changes else None
    )
    updated = await request_repo.update(
        ctx.db, request["_id"], changes, now=now, by=user.id, session=s, history=history,
    )
    if "status" in changes:
        await ctx.emitter(user).request_status(updated, s, from_status=before,
                                               event_id=event_id)
    return updated


async def cancel_planned_visits(
    ctx: Ctx, user: User, request: dict[str, Any], s: AsyncClientSession, reason: str | None
) -> None:
    """The request was cancelled: its planned visits are cancelled in the same transaction. A
    started visit is left alone, so work being done is still accepted (TRD §3.2.2)."""
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    for visit in await visit_repo.live_for_request(ctx.db, request["_id"], s):
        if visit["status"] != VStatus.PLANNED.value:
            continue
        result = lifecycle.cancel(visit, reason, now)
        updated = await visit_repo.update(
            ctx.db, visit["_id"], result.fields, now=now, by=user.id, session=s,
            expected_status=VStatus.PLANNED.value,
        )
        await emitter.visit(ev.VisitCancelled, "visit.cancelled", updated, request, s,
                            before=visit, reason=reason, by_request=True)


async def requests_by_id(
    ctx: Ctx, ids: list[str], s: AsyncClientSession | None = None
) -> dict[str, dict[str, Any]]:
    """The requests a page of visits belongs to (their reference and title)."""
    cursor = request_repo.col(ctx.db).find({"_id": {"$in": sorted(set(ids))}}, session=s)
    return {d["_id"]: d async for d in cursor}
