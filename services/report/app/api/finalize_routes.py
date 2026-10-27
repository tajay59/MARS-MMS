"""Finalizing and reopening a visit report (TRD 11.2; PRD RPT-4 to RPT-6; W17-5, W17-7, W17-10).

`finalize` only starts the saga: it checks the draft is signed by the lead, makes the report
`finalizing` (edits stop) and queues the job, then answers 202 at once; the page follows the
report until it is final or a draft again. Asking again while it runs changes nothing. `reopen`
makes a final report superseded and a new draft of the next version in one transaction, and the
visit is unlocked right after (or by the cron if operations does not answer). Both need a
connection (OFF-10).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, status
from mms_common.auth import User, actor_for, require_roles
from mms_common.errors import Conflict, NotFound
from mms_common.ids import UUID7_PATTERN, new_id
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api import presenters
from app.api.context import Ctx, CtxDep
from app.api.report_schemas import ReopenIn, ReportOut
from app.domain import finalize
from app.domain import readmodel as rm
from app.events import publish
from app.jobs.finalize import job_id, release_lock
from app.repo import reports, signatures

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
Admin = Annotated[User, Depends(require_roles("admin"))]
ReportId = Annotated[str, Path(pattern=UUID7_PATTERN)]


async def _record(user: User, ctx: Ctx, report_id: str) -> ReportOut:
    s = ctx.svc
    doc = await reports.get(s.db, report_id)
    assert doc is not None  # noqa: S101 - it was just read
    return presenters.report_out(
        user, doc, await signatures.for_report(s.db, report_id), s.settings.attestation)


@router.post("/{report_id}/finalize", status_code=status.HTTP_202_ACCEPTED)
async def finalize_report(
    report_id: ReportId, user: Worker, ctx: CtxDep, request: Request
) -> ReportOut:
    """RPT-5: make the signed draft final. The lead or an admin, once the lead has signed this
    version. 409 `lead_not_signed` until then. Answers at once; the report is `finalizing` while
    the visit is locked and the PDF is drawn."""
    s = ctx.svc
    doc = await reports.get(s.db, report_id)
    if doc is None:
        raise NotFound()
    finalize.may_finalize(doc, user.id, is_admin=user.is_admin)
    if doc["status"] == "finalizing":
        return await _record(user, ctx, report_id)  # already on its way: nothing more is queued
    signed = await signatures.valid(s.db, report_id, doc["version"])
    finalize.check_ready(doc, signed)
    actor = actor_for(request, user).model_dump()
    if not await reports.request_finalize(
        s.db, report_id, content_version=doc["content_version"],
        content_hash=doc["content_hash"], by=user.id, actor=actor, now=s.clock.now(),
    ):
        # The draft changed (or someone else started) between the read and the write
        current = await reports.get(s.db, report_id)
        if current is not None and current["status"] == "finalizing":
            return await _record(user, ctx, report_id)
        raise Conflict("The report changed. Read it again", code="content_changed")
    await s.jobs.enqueue(job_id(report_id))
    return await _record(user, ctx, report_id)


class _NotFinal(Exception):  # noqa: N818 - control flow inside a transaction body
    pass


@router.post("/{report_id}/reopen", status_code=status.HTTP_201_CREATED)
async def reopen_report(
    report_id: ReportId, body: ReopenIn, user: Admin, ctx: CtxDep, request: Request
) -> ReportOut:
    """RPT-6: an admin reopens a final report for correction. The final becomes `superseded` and
    stays readable; the next version is a draft with the same narrative and photo choice, the
    facts read again and no signatures. Answers with the new draft. 409 `already_reopened` when
    the version was already superseded, `not_final` when it is not final yet."""
    s = ctx.svc
    reason = finalize.reopen_reason(body.reason)
    old = await reports.get(s.db, report_id)
    if old is None:
        raise NotFound()
    if old["status"] == "superseded":
        raise Conflict("This report was already reopened", code="already_reopened")
    if old["status"] != "final":
        raise Conflict("Only a final report can be reopened", code="not_final")
    created_id = new_id()
    actor = actor_for(request, user)

    async def save(session: AsyncClientSession) -> None:
        current = await reports.get(s.db, report_id, session)
        if current is None or current["status"] != "final":
            raise _NotFinal
        draft = finalize.reopened_draft(
            current, report_id=created_id, reason=reason, by=user.id, now=s.clock.now())
        if not await reports.supersede(
            s.db, report_id, by=user.id, now=s.clock.now(), session=session
        ):
            raise _NotFinal
        if not await reports.insert_if_new(s.db, draft, session):
            raise _NotFinal
        row: dict[str, Any] | None = await s.db[rm.REQUESTS].find_one(
            {"_id": current["request_id"]}, session=session)
        await publish.reopened(
            s.db, s.clock, draft, previous_version=current["version"], reason=reason,
            reopened_by=user.id, request_status=row["status"] if row else None, actor=actor,
            session=session)

    try:
        await in_transaction(s.client, save)
    except _NotFinal:
        raise Conflict("This report was already reopened", code="already_reopened") from None
    created = await reports.get(s.db, created_id)
    assert created is not None  # noqa: S101 - it was just inserted
    await release_lock(s, created)  # the visit's boards open again; the cron retries if it fails
    return await _record(user, ctx, created_id)
