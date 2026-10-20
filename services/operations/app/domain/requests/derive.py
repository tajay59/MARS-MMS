"""`derive_status` (TRD §3.2.2, PRD §5.1, ADR-17). A pure function: given a request's visits it
says what status the request has from Assigned until closure. Visits arrive in Phase 4; the
function is built and tested now so the rules are fixed before anything depends on them.

The inputs are what the function reads, not the visit records themselves (`VisitFacts`), so
the visit module can change its documents without touching this rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.domain.requests.state import DERIVED, Status

VisitStatus = Literal["planned", "started", "ended", "cancelled"]


@dataclass(frozen=True)
class VisitFacts:
    status: VisitStatus
    ended_at: datetime | None = None
    additional_visit_required: bool = False
    report_status: str | None = None  # "final" once the visit report is final
    report_finalized_at: datetime | None = None


def _ended_at(visit: VisitFacts) -> datetime:
    return visit.ended_at or datetime.min.replace(tzinfo=UTC)


def _activity_after(ended: Sequence[VisitFacts], since: datetime) -> bool:
    """A visit ended, or a visit report was finalized, after the client's rejection."""
    return any(
        (v.ended_at is not None and v.ended_at > since)
        or (v.report_finalized_at is not None and v.report_finalized_at > since)
        for v in ended
    )


def derive_status(
    current: Status, visits: Sequence[VisitFacts], rework_since: datetime | None = None
) -> Status:
    """The status the request should have. Outside the derived range (`DERIVED`) nothing is
    derived and `current` comes back unchanged."""
    if current not in DERIVED:
        return current
    live = [v for v in visits if v.status != "cancelled"]
    if any(v.status == "started" for v in live):
        return Status.IN_PROGRESS
    if any(v.status == "planned" for v in live):
        return Status.SCHEDULED
    ended = [v for v in live if v.status == "ended"]
    if not ended:
        return Status.ASSIGNED
    # The most recent visit decides whether another is needed. Visits that ended at the same
    # moment are all "most recent": if any of them asks for another visit, one is needed.
    latest = max(_ended_at(v) for v in ended)
    if any(v.additional_visit_required for v in ended if _ended_at(v) == latest):
        return Status.ASSIGNED
    if any(v.report_status != "final" for v in ended):
        return Status.IN_PROGRESS  # waiting for a visit report
    if rework_since is not None and not _activity_after(ended, rework_since):
        return Status.ASSIGNED  # the client rejected it and nothing new has happened
    return Status.CLIENT_REVIEW
