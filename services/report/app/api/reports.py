"""Report jobs (TRD §3.4). Label sheets (QR-6) are the first; visit and summary reports follow
in Phases 6 and 7. A request starts a job and returns at once; the worker draws the PDF."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, status
from mms_common.auth import User, require_roles
from mms_common.errors import NotFound
from mms_common.ids import UUID7_PATTERN, new_id

from app.api.context import CtxDep
from app.api.schemas import JobOut, JobResult, LabelsIn
from app.domain import labels as rules
from app.domain.labels import JobStatus, JobType
from app.jobs.labels import CONTENT_TYPE, object_key
from app.repo import jobs
from app.services import Services

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Admin = Annotated[User, Depends(require_roles("admin"))]
Staff = Annotated[User, Depends(require_roles("technician", "admin", "viewer"))]
JobId = Annotated[str, Path(pattern=UUID7_PATTERN)]


@router.post("/labels", status_code=status.HTTP_202_ACCEPTED)
async def start_labels(body: LabelsIn, admin: Admin, ctx: CtxDep) -> JobOut:
    """QR-6. Starts a label sheet for the chosen stations; poll `GET /jobs/{id}`."""
    s = ctx.svc
    phone = rules.check_phone(body.contact_phone) or rules.check_phone(
        s.settings.label_contact_phone
    )
    now = s.clock.now()
    ids = list(dict.fromkeys(body.station_ids))  # the order given, each station once
    doc: dict[str, Any] = {
        "_id": new_id(), "type": JobType.LABELS.value,
        "params": {"station_ids": ids, "contact_phone": phone},
        "status": JobStatus.QUEUED.value, "attempts": 0, "result": None, "error": None,
        "requested_by": admin.id, "request_id": ctx.request_id,
        "created_at": now, "updated_at": now, "finished_at": None,
    }
    await jobs.insert(s.db, doc)
    await s.jobs.enqueue(doc["_id"])
    return await _out(s, doc)


@router.get("/jobs/{job_id}")
async def get_job(job_id: JobId, user: Staff, ctx: CtxDep) -> JobOut:
    """The job's state and, once it is done, a ten-minute download link. Only the person who
    asked can see it; anyone else gets 404 (rule 4)."""
    doc = await jobs.get(ctx.svc.db, job_id)
    if doc is None or doc["requested_by"] != user.id:
        raise NotFound()
    return await _out(ctx.svc, doc)


async def _out(s: Services, doc: dict[str, Any]) -> JobOut:
    result = None
    stored = doc.get("result")
    if isinstance(stored, dict) and doc["status"] == JobStatus.DONE.value:
        ttl = s.settings.get_url_ttl_s
        url = s.storage.get_url(
            s.settings.bucket_reports, object_key(str(doc["_id"])), ttl,
            content_type=CONTENT_TYPE, filename="station-labels.pdf",
        )
        result = JobResult(
            pages=stored["pages"], stations=stored["stations"], missing=stored["missing"],
            pdf_sha256=stored["pdf_sha256"], pdf_bytes=stored["pdf_bytes"], download_url=url,
            expires_at=s.clock.now() + timedelta(seconds=ttl),
        )
    return JobOut(
        id=str(doc["_id"]), type=JobType(doc["type"]), status=JobStatus(doc["status"]),
        error=doc.get("error") if isinstance(doc.get("error"), str) else None, result=result,
        created_at=doc["created_at"], finished_at=doc.get("finished_at"),
    )
