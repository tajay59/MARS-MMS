"""`GET /api/v1/dashboard` (PRD SUM-4 to SUM-6; TRD 3.4; W19-7): the figures of the page a person
lands on. One view per role, computed from the read model and kept for a minute."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from mms_common.auth import User, require_roles
from mms_common.errors import Forbidden
from mms_common.logging import get_logger
from pydantic import BaseModel, Field, TypeAdapter

from app.api import presenters
from app.api.context import CtxDep
from app.domain import dashboard as dash
from app.repo import dashboard as repo

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
log = get_logger(__name__)

Reader = Annotated[User, Depends(require_roles("technician", "admin", "viewer", "client"))]


class StatusCount(BaseModel):
    status: str
    count: int


class CountryRow(BaseModel):
    country: str
    operational: int
    degraded: int
    offline: int
    decommissioned: int
    total: int


class AwaitingReport(BaseModel):
    report_id: str
    number: str
    version: int
    visit_id: str
    request_id: str
    station_codes: list[str]
    lead_name: str | None
    age_days: int


class AdminFigures(BaseModel):
    requests_awaiting_approval: int
    unassigned_queue: int
    in_client_review: int
    calibrations_overdue: int
    calibrations_due_soon: int
    failed_calibrations: int
    reports_awaiting_finalization: int
    upcoming_visits: int


class AdminDashboard(BaseModel):
    view: Literal["admin"] = "admin"
    as_of: datetime
    figures: AdminFigures
    requests_by_status: list[StatusCount]
    stations_by_country: list[CountryRow]
    reports_awaiting: list[AwaitingReport]


class TechnicianFigures(BaseModel):
    my_assigned: int
    queue: int
    my_upcoming_visits: int
    my_reports_to_finalize: int


class TechnicianDashboard(BaseModel):
    view: Literal["technician"] = "technician"
    as_of: datetime
    figures: TechnicianFigures
    reports_to_finalize: list[AwaitingReport]


class StationStatusCounts(BaseModel):
    operational: int
    degraded: int
    offline: int
    decommissioned: int


class RecentReport(BaseModel):
    report_id: str
    number: str
    type: str
    version: int
    request_id: str | None
    finalized_at: datetime | None


class ClientFigures(BaseModel):
    open_requests: int
    awaiting_our_review: int
    upcoming_visits: int


class ClientDashboard(BaseModel):
    view: Literal["client"] = "client"
    as_of: datetime
    figures: ClientFigures
    stations: StationStatusCounts
    recent_reports: list[RecentReport]


Dashboard = Annotated[
    AdminDashboard | TechnicianDashboard | ClientDashboard, Field(discriminator="view")
]
_ADAPTER: TypeAdapter[Dashboard] = TypeAdapter(Dashboard)


async def admin_view(ctx: CtxDep, now: datetime) -> AdminDashboard:
    db = ctx.svc.db
    by_status = await repo.requests_by_status(db, None)
    counts = {r["status"]: r["count"] for r in by_status}
    overdue, soon = await repo.calibrations_due(db, now)
    total, oldest = await repo.drafts_awaiting(db)
    return AdminDashboard(
        as_of=now,
        figures=AdminFigures(
            requests_awaiting_approval=counts["submitted"], unassigned_queue=counts["approved"],
            in_client_review=counts["client_review"], calibrations_overdue=overdue,
            calibrations_due_soon=soon, failed_calibrations=await repo.failed_calibrations(db),
            reports_awaiting_finalization=total,
            upcoming_visits=await repo.upcoming_visits(db, now),
        ),
        requests_by_status=[StatusCount(**r) for r in by_status],
        stations_by_country=[CountryRow(**r) for r in await repo.stations_by_country(db)],
        reports_awaiting=[AwaitingReport(**dash.awaiting(r, now)) for r in oldest],
    )


async def technician_view(ctx: CtxDep, user: User, now: datetime) -> TechnicianDashboard:
    db = ctx.svc.db
    total, oldest = await repo.drafts_awaiting(db, lead_id=user.id)
    return TechnicianDashboard(
        as_of=now,
        figures=TechnicianFigures(
            my_assigned=await repo.my_assigned(db, user.id),
            queue=await repo.count_requests(db, None, "approved"),
            my_upcoming_visits=await repo.upcoming_visits(db, now, staff_id=user.id),
            my_reports_to_finalize=total,
        ),
        reports_to_finalize=[AwaitingReport(**dash.awaiting(r, now)) for r in oldest],
    )


async def client_view(ctx: CtxDep, user: User, now: datetime) -> ClientDashboard:
    db = ctx.svc.db
    org = user.org_id or ""  # a client always has one; "" matches nothing rather than everything
    by_status = await repo.requests_by_status(db, org)
    counts = {r["status"]: r["count"] for r in by_status}
    readable = [r for r in await repo.reports_for_client(db, org)
                if presenters.client_may_read(r, user)]
    return ClientDashboard(
        as_of=now,
        figures=ClientFigures(
            open_requests=sum(counts.values()), awaiting_our_review=counts["client_review"],
            upcoming_visits=await repo.upcoming_visits(db, now, org_id=org),
        ),
        stations=StationStatusCounts(**await repo.station_status(db, org)),
        recent_reports=[
            RecentReport(report_id=r["_id"], number=r["number"], type=r["type"],
                         version=r["version"], request_id=r.get("request_id"),
                         finalized_at=r.get("finalized_at"))
            for r in readable[:3]
        ],
    )


async def cached(ctx: CtxDep, key: str, build: Any) -> Dashboard:
    """The figures from Redis if a minute has not passed, else built and stored. Redis being
    down is not a reason to show nothing."""
    ttl = ctx.svc.settings.dashboard_cache_s
    redis = ctx.request.app.state.redis
    if ttl > 0:
        try:
            raw = await redis.get(key)
            if raw:
                return _ADAPTER.validate_json(raw)
        except Exception:  # noqa: BLE001 - a cache miss is the safe answer
            log.warning("dashboard_cache_read_failed", key=key)
    built: Dashboard = await build()
    if ttl > 0:
        try:
            await redis.set(key, _ADAPTER.dump_json(built), ex=ttl)
        except Exception:  # noqa: BLE001
            log.warning("dashboard_cache_write_failed", key=key)
    return built


@router.get("")
async def dashboard(
    user: Reader, ctx: CtxDep,
    view: Annotated[Literal["admin", "technician", "client"] | None, Query()] = None,
) -> Dashboard:
    """The caller's own view by default. Asking for one the role does not have is refused."""
    chosen = dash.view_for(user.roles, view)
    if chosen is None:
        raise Forbidden("This dashboard is not for your role", code="wrong_view")
    now = ctx.svc.clock.now()
    if chosen == "admin":
        return await cached(ctx, "dash:admin", lambda: admin_view(ctx, now))
    if chosen == "technician":
        return await cached(
            ctx, f"dash:technician:{user.id}", lambda: technician_view(ctx, user, now)
        )
    # Keyed by the caller's organization, never by anything in the request (rule 3)
    return await cached(ctx, f"dash:client:{user.org_id}", lambda: client_view(ctx, user, now))
