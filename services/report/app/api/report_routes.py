"""Visit reports (TRD 3.4; PRD RPT-1, RPT-3; W16): list, read, preview and download a draft.

Staff read drafts; attending staff and admins ask for a preview; a client sees final reports of
their own organization only (rule 6, rule 4). Editing and signing are in `edit_routes`;
finalizing and reopening arrive with the saga.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, Forbidden, NotFound
from mms_common.ids import UUID7_PATTERN

from app.api import presenters
from app.api.context import CtxDep
from app.api.report_schemas import DownloadOut, PreviewOut, ReportOut, ReportSummary
from app.domain import drafts, numbering
from app.jobs.drafts import job_id
from app.jobs.render_draft import CONTENT_TYPE
from app.repo import reports, signatures

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Reader = Annotated[User, Depends(require_roles("technician", "admin", "viewer", "client"))]
Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
ReportId = Annotated[str, Path(pattern=UUID7_PATTERN)]


@router.get("")
async def list_reports(
    user: Reader, ctx: CtxDep,
    subject_ref: Annotated[str | None, Query(max_length=80)] = None,
    type: Annotated[str | None, Query(pattern="^(visit|closeout|client_form)$")] = None,  # noqa: A002
) -> list[ReportSummary]:
    """Reports and their versions, newest version first. Clients: final ones of their own
    organization."""
    found = await reports.list_reports(ctx.svc.db, subject_ref=subject_ref, type_=type)
    return [ReportSummary(**presenters.summary(d)) for d in found
            if not user.is_client or presenters.client_may_read(d, user)]


@router.get("/{report_id}")
async def get_report(report_id: ReportId, user: Reader, ctx: CtxDep) -> ReportOut:
    s = ctx.svc
    doc = presenters.visible(user, await reports.get(s.db, report_id))
    signed = [] if user.is_client else await signatures.for_report(s.db, report_id)
    return presenters.report_out(user, doc, signed, s.settings.attestation)


@router.post("/{report_id}/preview", status_code=status.HTTP_202_ACCEPTED)
async def preview(report_id: ReportId, user: Worker, ctx: CtxDep) -> PreviewOut:
    """RPT-3: draw the draft as it is now. Answers `ready` when that PDF already exists, else
    queues one render (asking again while it runs queues nothing more) and answers `rendering`."""
    s = ctx.svc
    doc = await reports.get(s.db, report_id)
    if doc is None:
        raise NotFound()
    if not user.is_admin and user.id not in doc["staff_ids"]:
        raise Forbidden("Only the people attending can do this", code="not_attending")
    if doc["status"] != "draft":
        raise Conflict("Only a draft can be previewed", code="not_a_draft")
    if doc["facts_stale"] or doc["content"]["facts"] is None:
        raise Conflict("The draft is still being prepared", code="draft_not_ready")
    if drafts.pdf_is_current(doc):
        return PreviewOut(state="ready", pdf=presenters.pdf_state(doc))
    if await reports.request_render(s.db, report_id, s.clock.now()):
        await s.jobs.enqueue(job_id(report_id))
    doc = await reports.get(s.db, report_id)
    assert doc is not None  # noqa: S101 - it was just read
    return PreviewOut(state="rendering", pdf=presenters.pdf_state(doc))


@router.get("/{report_id}/download")
async def download(report_id: ReportId, user: Reader, ctx: CtxDep) -> DownloadOut:
    """A ten-minute link to the report's PDF (never cached: it acts as a password): the final
    one for a final or superseded version, else the latest draft. If a draft changed since its
    PDF was drawn, `current` is false and the link is to the older one."""
    s = ctx.svc
    doc = presenters.visible(user, await reports.get(s.db, report_id))
    final = doc["status"] in ("final", "superseded")
    pdf = doc.get("final_pdf") if final else doc.get("draft_pdf")
    if not pdf:
        raise Conflict("There is no PDF yet", code="no_pdf")
    ttl = s.settings.get_url_ttl_s
    name = numbering.file_name(doc["number"], doc["version"], draft=not final)
    url = s.storage.get_url(
        s.settings.bucket_reports, pdf["key"], ttl, content_type=CONTENT_TYPE, filename=name)
    return DownloadOut(
        url=url, expires_at=s.clock.now() + timedelta(seconds=ttl), filename=name,
        current=final or drafts.pdf_is_current(doc),
    )
