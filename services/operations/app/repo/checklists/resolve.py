"""What a visit to a station is given: its type's template and an add-on for each installed sensor
model (W10-11). Read by `GET /checklist-templates/resolve` and by a visit when it starts, which
copies the items so a template edited later changes nothing already started (VIS-8)."""

from __future__ import annotations

from typing import Any

from mms_common.errors import NotFound

from app.domain.checklists import templates
from app.repo.checklists import templates as repo
from app.repo.stations import models, units
from app.repo.stations import stations as station_repo
from app.repo.stations.common import Db, Session


async def for_station(
    db: Db, station_id: str, session: Session = None
) -> tuple[str | None, list[dict[str, Any]]]:
    """`(station type, items)`; raises NotFound for a station that does not exist."""
    station = await station_repo.get(db, station_id)
    if station is None:
        raise NotFound()
    station_type = station.get("type")
    installed = await units.installed_at(db, station_id)
    model_ids = sorted({u["model_id"] for u in installed})
    found = await models.by_ids(db, model_ids) if model_ids else {}
    keys = [templates.scope_key(None, m) for m in model_ids]
    if station_type:
        keys.append(templates.scope_key(station_type, None))
    active = await repo.active_for_scopes(db, keys)
    station_template = (active.get(templates.scope_key(station_type, None))
                        if station_type else None)
    add_ons = [
        templates.AddOn(
            model_id=m,
            label=f"{found[m]['manufacturer']} {found[m]['model']}" if m in found else m,
            template=active.get(templates.scope_key(None, m)),
        )
        for m in model_ids
    ]
    return station_type, templates.resolve(station_template, add_ons)
