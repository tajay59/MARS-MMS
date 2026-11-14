"""Summary reports (PRD SUM-1 to SUM-3; TRD 3.4; decisions W19-8, W19-9): ask for one, follow it,
download it. A request makes a job and returns at once; the worker reads the read model and writes
the file. The list and the file belong to the person who asked (anyone else: 404, rule 4).

Running a report changes nothing of anyone's work, so a Viewer may (the matrix says so). A client
may run three types for their own organization only, and the organization and the stations are
checked here and again where the rows are read."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from mms_common.auth import User, require_roles
from mms_common.errors import Forbidden, NotFound, ValidationFailed
from mms_common.ids import UUID7_PATTERN, new_id
from pydantic import BaseModel, ConfigDict, Field

from app.api.context import CtxDep
from app.domain import summary
from app.domain.labels import JobStatus, JobType
from app.domain.summary import Kind
from app.jobs.summary import CONTENT_TYPES
from app.repo import jobs
from app.repo import summary as data_repo
from app.services import Services

router = APIRouter(prefix="/api/v1/reports/summary", tags=["summary reports"])

Reader = Annotated[User, Depends(require_roles("technician", "admin", "viewer", "client"))]
JobId = Annotated[str, Path(pattern=UUID7_PATTERN)]
SAME_REQUEST_WINDOW = timedelta(minutes=1)


class SummaryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Kind
    format: Literal["pdf", "csv"] = "pdf"
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")
    org_id: Annotated[str | None, Field(pattern=UUID7_PATTERN)] = None
    country: Annotated[str | None, Field(min_length=2, max_length=60)] = None
    station_ids: Annotated[list[Annotated[str, Field(pattern=UUID7_PATTERN)]] | None,
                           Field(max_length=summary.MAX_STATIONS)] = None
    due_in_days: Annotated[int, Field(ge=1, le=365)] = 30


class SummaryType(BaseModel):
    type: Kind
    title: str
    description: str
    uses_period: bool
    formats: list[str]


class SummaryJob(BaseModel):
    id: str
    type: Kind
    format: Literal["pdf", "csv"]
    status: JobStatus
    error: str | None
    period_from: date | None
    period_to: date | None
    created_at: datetime
    finished_at: datetime | None
    file_name: str | None
    rows: int | None
    pages: int | None
    download_url: str | None
    expires_at: datetime | None


@router.get("/types")
async def types(user: Reader) -> list[SummaryType]:
    """What this person may ask for: a client three, staff all that are built."""
    return [
        SummaryType(type=t.key, title=t.title, description=t.description,
                    uses_period=t.uses_period, formats=["pdf", "csv"])
        for t in summary.TYPES.values() if summary.allowed(t.key, client=user.is_client)
    ]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start(body: SummaryIn, user: Reader, ctx: CtxDep) -> SummaryJob:
    s = ctx.svc
    info = summary.TYPES[body.type]
    if not summary.allowed(body.type, client=user.is_client):
        raise Forbidden("Clients can make three of these reports", code="not_for_clients")
    if info.uses_period:
        if body.from_date is None or body.to_date is None:
            raise ValidationFailed("Choose the first and last day", code="invalid_period")
        summary.period(body.from_date, body.to_date, s.settings.summary_time_zone,
                       s.settings.summary_max_days)
    org_id = body.org_id
    if user.is_client:
        # A client's report is their own organization's, whatever the request says (rule 3)
        if org_id and org_id != user.org_id:
            raise NotFound()
        org_id = user.org_id
    stations = sorted(set(body.station_ids)) if body.station_ids else None
    # Checked now, so a station outside the organization is a 404 and not a failed job later
    await data_repo.resolve(s.db, org_id=org_id, country=body.country, station_ids=stations)
    params: dict[str, Any] = {
        "type": body.type.value, "format": body.format,
        "from": body.from_date.isoformat() if info.uses_period and body.from_date else None,
        "to": body.to_date.isoformat() if info.uses_period and body.to_date else None,
        "org_id": org_id, "country": body.country, "station_ids": stations,
        "due_in_days": body.due_in_days if body.type is Kind.CALIBRATION_DUE else None,
    }
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    now = s.clock.now()
    again = await jobs.same_request(
        s.db, user.id, JobType.SUMMARY.value, key, now - SAME_REQUEST_WINDOW)
    if again is not None:
        return _out(s, again)
    doc: dict[str, Any] = {
        "_id": new_id(), "type": JobType.SUMMARY.value, "params": params, "params_key": key,
        "status": JobStatus.QUEUED.value, "attempts": 0, "result": None, "error": None,
        "requested_by": user.id, "requested_by_name": user.name, "request_id": ctx.request_id,
        "created_at": now, "updated_at": now, "finished_at": None,
    }
    await jobs.insert(s.db, doc)
    await s.jobs.enqueue(f"summary:{doc['_id']}")
    return _out(s, doc)


@router.get("/jobs")
async def mine(
    user: Reader, ctx: CtxDep, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[SummaryJob]:
    """The person's own summaries of the last `REPORT_SUMMARY_KEEP_DAYS` days, newest first."""
    s = ctx.svc
    since = s.clock.now() - timedelta(days=s.settings.summary_keep_days)
    found = await jobs.recent_for(s.db, user.id, JobType.SUMMARY.value, since, limit)
    return [_out(s, d) for d in found]


@router.get("/jobs/{job_id}")
async def get_job(job_id: JobId, user: Reader, ctx: CtxDep) -> SummaryJob:
    doc = await jobs.get(ctx.svc.db, job_id)
    if doc is None or doc["requested_by"] != user.id or doc["type"] != JobType.SUMMARY.value:
        raise NotFound()
    return _out(ctx.svc, doc)


def _out(s: Services, doc: dict[str, Any]) -> SummaryJob:
    params = doc["params"]
    result = doc.get("result") if isinstance(doc.get("result"), dict) else None
    url = expires = None
    if result and doc["status"] == JobStatus.DONE.value:
        ttl = s.settings.get_url_ttl_s
        url = s.storage.get_url(
            s.settings.bucket_reports, result["key"], ttl,
            content_type=CONTENT_TYPES[result["format"]], filename=result["file_name"])
        expires = s.clock.now() + timedelta(seconds=ttl)
    return SummaryJob(
        id=str(doc["_id"]), type=Kind(params["type"]), format=params["format"],
        status=JobStatus(doc["status"]),
        error=doc["error"] if isinstance(doc.get("error"), str) else None,
        period_from=date.fromisoformat(params["from"]) if params.get("from") else None,
        period_to=date.fromisoformat(params["to"]) if params.get("to") else None,
        created_at=doc["created_at"], finished_at=doc.get("finished_at"),
        file_name=result["file_name"] if result else None,
        rows=result["rows"] if result else None, pages=result["pages"] if result else None,
        download_url=url, expires_at=expires,
    )
