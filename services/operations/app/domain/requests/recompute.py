"""A request's status from its visits (ADR-17; TRD §3.2.2; W10-6). No I/O.

`derive_status` is the rule; this turns the visit documents into the facts it reads and says
what else follows (the first visit's start, a milestone). The route runs it inside the same
transaction as every visit change and writes what it returns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.requests.derive import VisitFacts, derive_status
from app.domain.requests.state import Status


@dataclass(frozen=True)
class Settled:
    status: Status
    first_visit_at: datetime | None  # when the first visit started, for the milestone


def facts_of(visit: Mapping[str, Any]) -> VisitFacts:
    return VisitFacts(
        status=visit["status"],
        ended_at=visit.get("ended_at"),
        additional_visit_required=bool(visit.get("additional_visit_required")),
        report_status=visit.get("report_status") or None,
        report_finalized_at=visit.get("report_finalized_at"),
    )


def recompute(request: Mapping[str, Any], visits: Sequence[Mapping[str, Any]]) -> Settled:
    """The status the request should have now, given all of its visits. Outside the derived
    statuses (`DERIVED`) it comes back unchanged."""
    status = derive_status(
        Status(request["status"]), [facts_of(v) for v in visits], request.get("rework_since")
    )
    started = [v["started_at"] for v in visits if v.get("started_at") is not None]
    return Settled(status=status, first_visit_at=min(started) if started else None)
