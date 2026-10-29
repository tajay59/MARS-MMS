"""The audit log for people (PRD AUD-4 to AUD-6, TRD §3.5; W19-1 to W19-5).

Admins search the whole trail, export it as CSV and run the integrity check. Staff and the
Viewer read one resource's History: who did what and when, without values (W19-2). A client
reads none of it. Looking at the trail leaves a record in it: an export and a check are
appended to the chain like any other change (W19-5).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import StreamingResponse
from mms_common import safecsv
from mms_common.auth import User, actor_for, require_roles, require_staff
from mms_common.errors import AppError, NotFound
from mms_common.ids import UUID7_PATTERN, new_id
from pydantic import BaseModel

from app.domain import audit_view
from app.domain.audit_view import EXPORT_MAX, HistoryType
from app.repo import audit, audit_checks

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

Admin = Annotated[User, Depends(require_roles("admin"))]
Staff = Annotated[User, Depends(require_staff())]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


class TooManyRecords(AppError):
    status, code, title = 422, "too_many_records", "Too many records to export"


class Who(BaseModel):
    user_id: str | None
    name: str | None
    roles: list[str]
    ip: str | None
    user_agent: str | None
    device_id: str | None


class Change(BaseModel):
    field: str
    before: Any
    after: Any


class AuditRecord(BaseModel):
    """The whole record (admins)."""

    seq: int
    event_id: str
    at: str | None
    received_at: str | None
    actor: Who
    action: str
    summary: str
    resource: dict[str, str] | None
    org_id: str | None
    changes: list[Change]
    before: Any
    after: Any
    metadata: dict[str, Any]
    correlation_id: str | None
    source_service: str | None
    hash: str
    prev_hash: str


class AuditPage(BaseModel):
    items: list[AuditRecord]
    next_cursor: int | None
    total: int  # how many match, no higher than the export limit
    over_export_limit: bool


class HistoryEntry(BaseModel):
    """What a History tab shows (staff, Viewer): no address, device, values or data."""

    seq: int
    at: str | None
    actor_name: str | None
    actor_role: str | None
    action: str
    summary: str
    changed_fields: list[str]


class HistoryPage(BaseModel):
    items: list[HistoryEntry]
    next_cursor: int | None


class CheckOut(BaseModel):
    id: str
    kind: Literal["manual", "nightly"]
    status: Literal["queued", "running", "passed", "broken", "failed"]
    checked: int
    total: int | None
    first_break_seq: int | None
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    requested_by_name: str | None


class Filters:
    """The search as query parameters, shared by the list and the export."""

    def __init__(
        self,
        actor: Annotated[str | None, Query(max_length=100)] = None,
        action: Annotated[
            str | None, Query(pattern=r"^[a-z_]+(\.[a-z_]+)*$", max_length=64)
        ] = None,
        resource_type: Annotated[str | None, Query(pattern=r"^[a-z_]+$", max_length=40)] = None,
        resource_id: Annotated[str | None, Query(pattern=r"^[0-9A-Za-z._:-]+$", max_length=64)]
        = None,
        org_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> None:
        def utc(value: datetime | None) -> datetime | None:
            if value is None:
                return None
            return value if value.tzinfo else value.replace(tzinfo=UTC)

        start, end = utc(since), utc(until)
        self.filter = audit.match(
            actor=actor, action=action, resource_type=resource_type, resource_id=resource_id,
            org_id=org_id, since=start, until=end,
        )
        self.echo = {k: v for k, v in {
            "actor": actor, "action": action, "resource_type": resource_type,
            "resource_id": resource_id, "org_id": org_id,
            "since": start.isoformat() if start else None,
            "until": end.isoformat() if end else None,
        }.items() if v}


Search = Annotated[Filters, Depends()]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[int | None, Query(ge=1)]


@router.get("/events")
async def search_events(
    request: Request, _: Admin, filters: Search, cursor: Cursor = None, limit: Limit = 50,
) -> AuditPage:
    db = request.app.state.audit_db
    rows = await audit.search(db, filters.filter, before_seq=cursor, limit=limit + 1)
    page, more = rows[:limit], len(rows) > limit
    total = await audit.count(db, filters.filter, EXPORT_MAX)
    return AuditPage(
        items=[AuditRecord(**audit_view.admin_view(r)) for r in page],
        next_cursor=page[-1]["seq"] if more else None,
        total=min(total, EXPORT_MAX),
        over_export_limit=total > EXPORT_MAX,
    )


@router.get("/events/export.csv")
async def export_events(request: Request, user: Admin, filters: Search) -> StreamingResponse:
    db = request.app.state.audit_db
    clock = request.app.state.clock
    total = await audit.count(db, filters.filter, EXPORT_MAX)
    if total > EXPORT_MAX:
        raise TooManyRecords(
            f"More than {EXPORT_MAX:,} records match. Narrow the dates or the filters, then "
            "export again."
        )
    await audit.record_own(request.app.state.audit_mongo, db, audit_view.own_record(
        action="audit.exported", at=clock.now(), actor=actor_for(request, user).model_dump(),
        correlation_id=getattr(request.state, "request_id", None), event_id=new_id(),
        metadata={"records": total, "filters": filters.echo},
    ))

    async def body() -> AsyncIterator[str]:
        writer = safecsv.Writer()
        yield writer.header(audit_view.export_header())
        async for record in audit.stream(db, filters.filter):
            yield writer.line(audit_view.export_row(record))

    name = f"audit-log-{clock.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        body(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"',
                 "Cache-Control": "no-store"},
    )


@router.get("/resources/{kind}/{thing_id}")
async def history(
    request: Request, _: Staff, kind: HistoryType, thing_id: IdPath, cursor: Cursor = None,
    limit: Limit = 50,
) -> HistoryPage:
    flt = audit.history_filter(kind, thing_id)
    rows = await audit.search(request.app.state.audit_db, flt, before_seq=cursor, limit=limit + 1)
    page = rows[:limit]
    return HistoryPage(
        items=[HistoryEntry(**audit_view.staff_view(r)) for r in page],
        next_cursor=page[-1]["seq"] if len(rows) > limit else None,
    )


def _check_out(doc: dict[str, Any]) -> CheckOut:
    by = doc.get("requested_by") or {}
    return CheckOut(
        id=doc["_id"], kind=doc["kind"], status=doc["status"], checked=doc.get("checked", 0),
        total=doc.get("total"), first_break_seq=doc.get("first_break_seq"),
        requested_at=doc["requested_at"], started_at=doc.get("started_at"),
        finished_at=doc.get("finished_at"), requested_by_name=by.get("name"),
    )


@router.post("/verify", status_code=202)
async def start_check(request: Request, user: Admin) -> CheckOut:
    """Queue an integrity check of the chain (AUD-5). A worker takes it within seconds."""
    db, clock = request.app.state.db, request.app.state.clock
    check_id = new_id()
    by = {"user_id": user.id, "name": user.name, "roles": sorted(user.roles)}
    await audit_checks.create(db, check_id=check_id, kind="manual", now=clock.now(), by=by)
    doc = await audit_checks.get(db, check_id)
    if doc is None:
        raise NotFound()
    return _check_out(doc)


@router.get("/checks/latest")
async def latest_check(request: Request, _: Admin) -> CheckOut:
    """The last check that finished, by an admin or the nightly run."""
    doc = await audit_checks.latest_finished(request.app.state.db)
    if doc is None:
        raise NotFound("No check has finished yet")
    return _check_out(doc)


@router.get("/checks/{check_id}")
async def get_check(request: Request, _: Admin, check_id: IdPath) -> CheckOut:
    doc = await audit_checks.get(request.app.state.db, check_id)
    if doc is None:
        raise NotFound()
    return _check_out(doc)
