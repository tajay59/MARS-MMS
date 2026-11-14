"""The visit lock and the visit's report status (VIS-12; TRD 3.2, 11.2; W17-8, W17-9). No I/O.

Finalizing a visit report locks the visit's boards: the report service asks operations to lock the
visit for one version of one report, and to unlock it when that finalize fails or the report is
reopened. A lock belongs to a `(report_id, version)` pair, so a repeat of the same call changes
nothing and a late unlock for an old version cannot open a visit that a newer one locked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mms_common.errors import Conflict

from app.domain.visits.state import VStatus

REPORT_NONE = "none"
REPORT_DRAFT = "draft"
REPORT_FINAL = "final"


@dataclass(frozen=True)
class Change:
    """The fields to write (empty when the call changes nothing) and whether the visit is
    locked afterwards."""

    fields: dict[str, Any]
    locked: bool


def holder(visit: Mapping[str, Any]) -> tuple[str, int] | None:
    """The report version holding the lock, or None when the visit is not locked."""
    held = visit.get("locked_for")
    if not visit.get("locked") or not held:
        return None
    return held["report_id"], held["version"]


def lock(visit: Mapping[str, Any], report_id: str, version: int, at: datetime) -> Change:
    """Lock an ended visit for this report version. The same pair again is a no-op; another pair
    on a locked visit is refused, so two finalizes can never both believe they hold the visit."""
    if visit["status"] != VStatus.ENDED.value:
        raise Conflict("Only an ended visit can be locked", code="not_ended")
    held = holder(visit)
    if held == (report_id, version):
        return Change({}, True)
    if visit.get("locked"):
        raise Conflict("This visit is locked for another report version",
                       code="locked_by_another_report")
    return Change(
        {"locked": True, "locked_for": {"report_id": report_id, "version": version},
         "locked_at": at},
        True,
    )


def unlock(visit: Mapping[str, Any], report_id: str, version: int) -> Change:
    """Unlock the visit if this report version holds the lock. Anything else changes nothing and
    says so (`locked` stays what it is), so a late call is harmless."""
    held = holder(visit)
    if held is None:
        return Change({}, False)
    if held != (report_id, version):
        return Change({}, True)
    return Change({"locked": False, "locked_for": None, "locked_at": None}, False)


def finalized(
    visit: Mapping[str, Any], report_id: str, version: int, finalized_at: datetime
) -> dict[str, Any]:
    """The visit's report fields after `report.finalized`, or `{}` when the event is older than
    what the visit already knows (the report's version guards the write)."""
    known = visit.get("report_version")
    if known is not None and version < known:
        return {}
    if known == version and visit.get("report_status") == REPORT_FINAL:
        return {}
    return {
        "report_status": REPORT_FINAL, "report_id": report_id, "report_version": version,
        "report_finalized_at": finalized_at,
    }


def reopened(visit: Mapping[str, Any], report_id: str, version: int) -> dict[str, Any]:
    """The visit's report fields after `report.reopened` (`version` is the new draft's), or `{}`
    for an event older than what the visit knows."""
    known = visit.get("report_version")
    if known is not None and version < known:
        return {}
    if known == version and visit.get("report_status") == REPORT_DRAFT:
        return {}
    return {
        "report_status": REPORT_DRAFT, "report_id": report_id, "report_version": version,
        "report_finalized_at": None,
    }
