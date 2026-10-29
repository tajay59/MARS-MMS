"""`POST /api/v1/sync`: a phone's queued operations, applied in order (TRD §3.2.1, §7.2 to §7.4;
PRD OFF-5, OFF-7, OFF-11; W14-1 to W14-5).

This is a dispatcher, not a second implementation. Each operation is run by calling the route
function that serves it online, with the caller's `User` and `Ctx`, so scoping, roles, validation,
events and the outbox are the same code (rules 2 to 6). What a route raises becomes an answer
(`domain/sync.py`); an operation applied is remembered by its `op_id` so asking again returns it;
a failed operation stops the later ones of its visit and no others.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from mms_common import metrics
from mms_common.auth import User, require_roles
from mms_common.errors import ValidationFailed
from pydantic import BaseModel, ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx, CtxDep
from app.api.sync_schemas import (
    AnswerOut,
    CreatePayload,
    DeletePayload,
    EndPayload,
    MediaAddPayload,
    MediaRemovePayload,
    StartPayload,
    StationAt,
    SyncIn,
    SyncOut,
    UpdatePayload,
)
from app.api.visits import element_routes, visit_routes
from app.domain import sync as rules
from app.events.publish import ev
from app.repo.requests import requests as request_repo
from app.repo.sync import claim, first_report, set_result, stored
from app.repo.visits import visits as visit_repo

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

Worker = Annotated[User, Depends(require_roles("technician", "admin"))]

Runner = Callable[[Ctx, User, str, Any], Awaitable[BaseModel | None]]


async def _start(ctx: Ctx, user: User, visit_id: str, p: StartPayload) -> BaseModel:
    return await visit_routes.start_visit(visit_id, p, user, ctx)


async def _arrive(ctx: Ctx, user: User, visit_id: str, p: StationAt) -> BaseModel:
    return await visit_routes.arrive(visit_id, p.station_id, p, user, ctx)


async def _depart(ctx: Ctx, user: User, visit_id: str, p: StationAt) -> BaseModel:
    return await visit_routes.depart(visit_id, p.station_id, p, user, ctx)


async def _end(ctx: Ctx, user: User, visit_id: str, p: EndPayload) -> BaseModel:
    return await visit_routes.end_visit(visit_id, p, user, ctx)


async def _create(ctx: Ctx, user: User, visit_id: str, p: CreatePayload) -> BaseModel:
    return await element_routes.add_element(visit_id, p.station_id, p, user, ctx, Response())


async def _update(ctx: Ctx, user: User, visit_id: str, p: UpdatePayload) -> BaseModel:
    return await element_routes.save_element(visit_id, p.station_id, p.element_id, p, user, ctx)


async def _delete(ctx: Ctx, user: User, visit_id: str, p: DeletePayload) -> None:
    await element_routes.delete_element(
        visit_id, p.station_id, p.element_id, user, ctx, p.base_version)


async def _media_add(ctx: Ctx, user: User, visit_id: str, p: MediaAddPayload) -> BaseModel:
    return await element_routes.add_element_media(
        visit_id, p.station_id, p.element_id, p, user, ctx)


async def _media_remove(ctx: Ctx, user: User, visit_id: str, p: MediaRemovePayload) -> BaseModel:
    return await element_routes.remove_element_media(
        visit_id, p.station_id, p.element_id, p.media_id, user, ctx)


# type -> (payload model, runner)
HANDLERS: dict[str, tuple[type[BaseModel], Callable[..., Awaitable[BaseModel | None]]]] = {
    "visit.start": (StartPayload, _start),
    "station.arrive": (StationAt, _arrive),
    "station.depart": (StationAt, _depart),
    "visit.end": (EndPayload, _end),
    "element.create": (CreatePayload, _create),
    "element.update": (UpdatePayload, _update),
    "element.delete": (DeletePayload, _delete),
    "element.media_add": (MediaAddPayload, _media_add),
    "element.media_remove": (MediaRemovePayload, _media_remove),
}


def _dump(result: BaseModel | None) -> dict[str, Any] | None:
    return result.model_dump(mode="json") if result is not None else None


async def _run_one(ctx: Ctx, user: User, op: Any, device_id: str) -> rules.Answer:
    """Check the envelope and the payload, run the operation, and answer. Never raises."""
    if (answer := rules.stale_version(op.op_id, op.v)) is not None:
        return answer
    handler = HANDLERS.get(op.type)
    if handler is None:
        return rules.Answer(op.op_id, "error", code="unknown_type",
                            message=f"This server does not know the change {op.type}")
    model, run = handler
    try:
        payload = model.model_validate(op.payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return rules.classify(op.op_id, ValidationFailed(
            f"{where}: {first['msg']}", code="bad_payload", field=where))
    async def remember(s: AsyncClientSession) -> None:
        await claim(ctx.db, op_id=op.op_id, user_id=user.id, device_id=device_id,
                    type_=op.type, visit_id=op.visit_id, now=ctx.clock.now(), session=s)

    try:
        # The operation's own transaction also writes its record, so the two never part
        result = await run(replace(ctx, tx_hooks=(remember,)), user, op.visit_id, payload)
    except Exception as exc:  # noqa: BLE001 - every failure becomes an answer for this operation
        return rules.classify(op.op_id, exc)
    dumped = _dump(result)
    await set_result(ctx.db, op.op_id, dumped)
    return rules.Answer(op.op_id, "applied", result=dumped)


async def _tell_of_conflicts(
    ctx: Ctx, user: User, found: dict[tuple[str, str], list[str]],
) -> None:
    """One `visit.sync_conflict` per visit and reason, once a day while it stays stuck."""
    if not found:
        return
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> None:
        for (visit_id, reason), op_types in found.items():
            visit = await visit_repo.get(ctx.db, visit_id, None, s)
            if visit is None or not await first_report(
                    ctx.db, visit_id=visit_id, user_id=user.id, reason=reason, now=now, session=s):
                continue
            request = await request_repo.require(ctx.db, visit["request_id"], None, s)
            await emitter.visit(
                ev.VisitSyncConflict, "visit.sync_conflict", visit, request, s,
                user_id=user.id, reason=reason, op_types=sorted(set(op_types)),
            )

    await ctx.tx(save)


@router.post("")
async def sync(body: SyncIn, user: Worker, ctx: CtxDep) -> SyncOut:
    """OFF-5: apply a batch of offline operations in order. Always 200 for a well-formed batch:
    each operation has its own answer (`applied`, `duplicate`, `conflict`, `error`, `skipped`)."""
    seen = await stored(ctx.db, [op.op_id for op in body.ops])
    batch = rules.Batch()
    answers: list[rules.Answer] = []
    reported: list[tuple[str, str, rules.Answer]] = []
    for op in body.ops:
        known = seen.get(op.op_id)
        if known is not None:
            if known["user_id"] != user.id:
                answer = rules.Answer(op.op_id, "error", code="not_yours",
                                      message="This change belongs to someone else")
            else:
                answer = rules.Answer(op.op_id, "duplicate", result=known.get("result"))
        elif batch.waits(op.visit_id):
            answer = rules.skipped(op.op_id)
        else:
            answer = await _run_one(ctx, user, op, body.device_id)
        batch.settle(op.visit_id, answer)
        answers.append(answer)
        reported.append((op.visit_id, op.type, answer))
    await _tell_of_conflicts(ctx, user, rules.conflicts_to_report(reported))
    for a in answers:
        metrics.SYNC_OPS.labels(a.status, a.code or "none").inc()
    return SyncOut(answers=[
        AnswerOut(op_id=a.op_id, status=a.status, code=a.code, message=a.message,
                  retryable=a.retryable, current=a.current, result=a.result)
        for a in answers
    ])
