"""A station's work record (TRD §3.2 `PUT .../work`; PRD VIS-7; W11-1, W11-2).

Only the station's owner (or an admin) writes it, while the visit is under way or has ended and is
not locked by its report. It is saved whole with `base_version`: a stale save is 409
`work_changed` and nothing is merged (ADR-18). The same content sent again is recognised and
changes nothing, so a retry after a lost answer is safe. The record, the visit's version and the
event are one Mongo transaction (rule 2).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, NotFound
from mms_common.ids import UUID7_PATTERN
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import CtxDep
from app.api.visits.schemas import VisitOut
from app.api.visits.work_schemas import WorkIn
from app.domain.visits import work
from app.events.publish import ev
from app.repo.checklists import resolve
from app.repo.requests import requests as request_repo
from app.repo.visits import visits as repo

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])

Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


def _station(visit: dict[str, Any], station_id: str) -> dict[str, Any]:
    for station in visit["stations"]:
        if station["station_id"] == station_id:
            found: dict[str, Any] = station
            return found
    raise NotFound()


@router.put("/{id}/stations/{station_id}/work")
async def save_work(
    id: IdPath, station_id: IdPath, body: WorkIn, user: Worker, ctx: CtxDep
) -> VisitOut:
    """VIS-7: the owner saves what was found and done at the station."""
    visit = await repo.require(ctx.db, id)
    station = _station(visit, station_id)
    work.check_can_save(visit, station, user.id, user.is_admin)
    now = ctx.clock.now()
    current = station.get("work")
    if current is None:  # started before records existed: copy the templates now
        _, items = await resolve.for_station(ctx.db, station_id)
        current = work.blank(items, now)
    cleaned = work.clean_record(body.record(), current)
    stored = work.save(current, cleaned, body.base_version, user.id, body.device_id, now)
    request = await request_repo.require(ctx.db, visit["request_id"])
    if stored is None:  # already saved: same content
        return VisitOut.build(visit, request, user)

    emitter = ctx.emitter(user)
    holder: dict[str, Any] = {}

    async def save(s: AsyncClientSession) -> None:
        updated = await repo.set_work(
            ctx.db, id, station_id, stored, base_version=body.base_version, now=now,
            by=user.id, session=s,
        )
        if updated is None:
            fresh = await repo.require(ctx.db, id, None, s)
            work.check_can_save(fresh, _station(fresh, station_id), user.id, user.is_admin)
            raise Conflict("This work record was changed since you opened it. Reload it",
                           code="work_changed")
        await emitter.visit(
            ev.VisitWorkUpdated, "visit.work_updated", updated, request, s, before=visit,
            station_id=station_id, version=stored["version"],
            sensor_actions=[
                {"id": a["id"], "action": a["action"]} for a in stored["sensor_actions"]
            ],
            config_versions=[v["id"] for v in stored["config_versions"]],
        )
        holder["doc"] = updated

    await ctx.tx(save)
    return VisitOut.build(holder["doc"], request, user)
