"""The client's answer to Client Review (PRD REQ-12, REQ-13; TRD 3.2, 11.3; AFD J8; decisions
W18-1 to W18-6).

`POST /requests/{id}/accept` closes the request on the client's signature. `POST
/requests/{id}/reject` sends it back to the same staff with the reason. Both name the review
they answered (`reviewing`), run in one transaction with their events (rule 2) and are safe to
send twice. Clients only; another organization's request is 404 (rule 4).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from mms_common.auth import User, require_roles
from mms_common.auth.deps import client_ip
from mms_common.ids import UUID7_PATTERN, new_id
from mms_common.signature import png_bytes, typed_name
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx, CtxDep
from app.api.requests.request_routes import _detail, _entry
from app.api.requests.schemas import AcceptIn, RejectIn, RequestDetail
from app.domain.requests import review
from app.domain.requests.state import MILESTONES, Action, Status, Who, transition
from app.events.publish import ev
from app.events.settle import history_entry
from app.repo.requests import requests as repo
from app.repo.visits import visits as visit_repo

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])

Client = Annotated[User, Depends(require_roles("client"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


async def _in_review(
    ctx: Ctx, request_id: str, action: Action, reviewing: Any, s: AsyncClientSession,
    reason: str | None = None,
) -> dict[str, Any]:
    """The request as the transaction sees it, still in the review the client answered. Another
    answer, the auto-close or a reopened report may have come first (they write the same
    record, so one of two concurrent transactions retries and lands here)."""
    fresh = await repo.require(ctx.db, request_id, None, s)
    transition(Status(fresh["status"]), action, Who.CLIENT, reason=reason)  # 409 `bad_transition`
    review.check_reviewing(fresh.get("review_started_at"), reviewing)
    return fresh


@router.post("/{id}/accept")
async def accept_request(
    id: IdPath, body: AcceptIn, user: Client, ctx: CtxDep, request: Request
) -> RequestDetail:
    """REQ-13: the client signs the work off. The request closes, the decision keeps the drawing,
    the typed name, the wording shown, the time, address and browser, and the visit reports in
    force. The drawing is stored here only; `request.closed` does not carry it."""
    current = await repo.require(ctx.db, id, user)
    if review.is_repeat(current, user.id, "accepted", body.reviewing):
        return await _detail(ctx, current, user)
    transition(Status(current["status"]), Action.ACCEPT, Who.CLIENT)
    review.check_reviewing(current.get("review_started_at"), body.reviewing)
    image, _, _ = png_bytes(
        body.image, max_bytes=ctx.settings.signature_max_bytes,
        max_width=ctx.settings.signature_max_width, max_height=ctx.settings.signature_max_height,
    )
    typed = typed_name(body.typed_name)
    comment = body.comment.strip() if body.comment else None
    signed = review.signature(
        typed=typed, image=image, attestation=ctx.settings.client_attestation,
        ip=client_ip(request), user_agent=(request.headers.get("User-Agent") or "")[:256] or None,
    )
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    event_id = new_id()

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        fresh = await _in_review(ctx, id, Action.ACCEPT, body.reviewing, s)
        visits = await visit_repo.for_request(ctx.db, id, None, s)
        milestones = dict(fresh.get("milestones", {}))
        milestones.setdefault(MILESTONES[Status.CLOSED], now)
        record = review.decision(
            "accepted", user_id=user.id, name=user.name, at=now,
            reviewing=fresh["review_started_at"], comment=comment,
            reports=review.final_reports(visits), signature=signed,
        )
        updated = await repo.update(
            ctx.db, id, {"status": Status.CLOSED.value, "milestones": milestones,
                         "client_verification": record},
            now=now, by=user.id, session=s, expected_status=Status.CLIENT_REVIEW.value,
            history=_entry(from_status=Status.CLIENT_REVIEW.value, to=Status.CLOSED, user=user,
                           now=now, event_id=event_id, note=comment or "Accepted by the client"),
        )
        await emitter.request(ev.RequestClosed, "request.closed", updated, s, before=fresh,
                              outcome="accepted", auto_closed=False, by_id=user.id)
        await emitter.request_status(updated, s, from_status=Status.CLIENT_REVIEW.value,
                                     event_id=event_id)
        return updated

    return await _detail(ctx, await ctx.tx(save), user)


@router.post("/{id}/reject")
async def reject_request(
    id: IdPath, body: RejectIn, user: Client, ctx: CtxDep
) -> RequestDetail:
    """REQ-13: the client sends the work back. In one transaction the request goes Client Review
    to Reopened and straight on to Assigned with the same staff; the review clock stops and the
    rework period starts (`rework_since`). The staff and admins are told the reason."""
    current = await repo.require(ctx.db, id, user)
    if review.is_repeat(current, user.id, "rejected", body.reviewing):
        return await _detail(ctx, current, user)
    transition(Status(current["status"]), Action.REJECT, Who.CLIENT, reason=body.reason)
    review.check_reviewing(current.get("review_started_at"), body.reviewing)
    reason = body.reason.strip()
    now = ctx.clock.now()
    emitter = ctx.emitter(user)
    first_event, second_event = new_id(), new_id()

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        fresh = await _in_review(ctx, id, Action.REJECT, body.reviewing, s, reason)
        record = review.decision(
            "rejected", user_id=user.id, name=user.name, at=now,
            reviewing=fresh["review_started_at"], comment=reason, reports=None,
        )
        reopened = await repo.update(
            ctx.db, id,
            {"status": Status.REOPENED.value, "rework_since": now, "review_started_at": None,
             "reminders_sent": [], "reopen_count": int(fresh.get("reopen_count") or 0) + 1,
             "client_verification": record},
            now=now, by=user.id, session=s, expected_status=Status.CLIENT_REVIEW.value,
            history=_entry(from_status=Status.CLIENT_REVIEW.value, to=Status.REOPENED, user=user,
                           now=now, event_id=first_event, note=reason),
        )
        await emitter.request(ev.RequestReopened, "request.reopened", reopened, s, before=fresh,
                              comment=reason, by_id=user.id)
        await emitter.request_status(reopened, s, from_status=Status.CLIENT_REVIEW.value,
                                     event_id=first_event, reason=reason)
        # Reopened is a moment, not a place to wait: the same staff have it again at once
        back = transition(Status.REOPENED, Action.RETURN, Who.SYSTEM)
        returned = await repo.update(
            ctx.db, id, {"status": back.value}, now=now, by=None, session=s,
            expected_status=Status.REOPENED.value,
            history=history_entry(from_status=Status.REOPENED.value, to=back, by=None,
                                  by_name=None, now=now, event_id=second_event,
                                  note="Returned to the same staff"),
        )
        await emitter.request_status(returned, s, from_status=Status.REOPENED.value,
                                     event_id=second_event)
        return returned

    return await _detail(ctx, await ctx.tx(save), user)
