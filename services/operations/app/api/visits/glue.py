"""What every visit change does to its request, in the change's own transaction (ADR-17, W10-6).

A route that changes a visit (a) takes the request's lock, (b) writes the visit and its event,
(c) calls `settle`, which reads all the request's visits, derives the status and writes it with
its history entry and `request.status_changed`. All of it is one Mongo transaction (rule 2), so
the request, its visits and the outbox never disagree.
"""

from __future__ import annotations

from typing import Any

from mms_common.auth import User
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx
from app.domain.visits import lifecycle
from app.domain.visits.state import VStatus
from app.events.publish import ev
from app.events.settle import lock_request as take_request
from app.events.settle import settle_request
from app.repo.requests import requests as request_repo
from app.repo.visits import visits as visit_repo


async def lock_request(ctx: Ctx, request_id: str, s: AsyncClientSession) -> dict[str, Any]:
    """Take the request, so two visit changes on it queue up (see `events.settle`)."""
    return await take_request(ctx.db, request_id, s)


async def settle(
    ctx: Ctx, user: User, request: dict[str, Any], s: AsyncClientSession, *, note: str
) -> dict[str, Any]:
    """Derive the request's status from its visits (read inside the transaction) and write it
    when it moved, with the first visit's start as a milestone. Returns the request as it is."""
    return await settle_request(
        ctx.db, ctx.clock, ctx.emitter(user), request, s, by=user.id, by_name=user.name, note=note,
    )


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
