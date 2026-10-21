"""What the person looking at a visit may do now, so a page shows only those buttons (viewers and
clients have none). The routes check again: this only mirrors them. No I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.visits.schedule import can_attend, can_manage
from app.domain.visits.state import VStatus


def visit_actions(
    visit: Mapping[str, Any], user_id: str, is_admin: bool, assigned_ids: Sequence[str]
) -> list[str]:
    status = VStatus(visit["status"])
    out: list[str] = []
    if status is VStatus.PLANNED:
        if can_manage(user_id, is_admin, visit, assigned_ids):
            # Owners change with the plan while it is planned (PATCH, W10-3)
            out += ["reschedule", "cancel", "change_owner"]
        if can_attend(user_id, is_admin, visit):
            out.append("start")
    elif status is VStatus.STARTED:
        if can_attend(user_id, is_admin, visit):
            out.append("end")
        if is_admin or user_id == visit["lead_staff_id"]:
            out.append("change_owner")
    elif status is VStatus.CANCELLED and is_admin:
        out.append("restore")
    return out


def station_actions(
    visit: Mapping[str, Any], station: Mapping[str, Any], user_id: str, is_admin: bool
) -> list[str]:
    """Arrive, then depart, for the station's owner (or an admin) while the visit is started."""
    if VStatus(visit["status"]) is not VStatus.STARTED:
        return []
    if not (is_admin or station["owner_staff_id"] == user_id):
        return []
    if station["arrived_at"] is None:
        return ["arrive"]
    if station["departed_at"] is None:
        return ["depart"]
    return []
