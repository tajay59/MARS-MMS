"""The queue (PRD REQ-7; AFD J4 step 4b, J5 step 1; TRD §3.2): approved requests nobody has
taken, oldest approval first. Staff only: a client has no queue (404, rule 4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from mms_common.auth import User, require_roles
from mms_common.errors import NotFound

from app.api.context import CtxDep
from app.api.requests.request_routes import _names
from app.api.requests.schemas import QueueItem, QueuePage
from app.repo.requests import requests as repo
from app.repo.stations import stations as station_repo

router = APIRouter(prefix="/api/v1/queue", tags=["requests"])

Reader = Annotated[User, Depends(require_roles())]


@router.get("")
async def get_queue(
    viewer: Reader,
    ctx: CtxDep,
    country: Annotated[str | None, Query(pattern="^[A-Z]{2}$")] = None,
    category: Annotated[str | None, Query(max_length=32)] = None,
    priority: Annotated[str | None, Query(max_length=16)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> QueuePage:
    """Everything waiting, with the filters the list has (a queue is short: no paging)."""
    if viewer.is_client:
        raise NotFound()
    station_ids = (
        tuple(await station_repo.ids_where(ctx.db, country=country, station_id=None))
        if country else None
    )
    f = repo.Filters(
        statuses=("approved",), unassigned=True, station_ids=station_ids, category=category,
        priority=priority, q=q.strip() if q and q.strip() else None,
    )
    found, total = await repo.queue(ctx.db, viewer, f, limit=limit)
    stations, org_names = await _names(ctx.db, found)
    return QueuePage(
        items=[QueueItem.waiting(d, stations, org_names) for d in found], total=total
    )
