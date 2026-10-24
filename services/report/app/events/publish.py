"""The report service's events, written in the transaction that changes the record (rule 2)."""

from __future__ import annotations

from typing import Any

from mms_common import outbox
from mms_common.events import Actor, Envelope, Resource
from mms_common.events import report as ev
from mms_common.ids import new_id
from mms_common.time import Clock
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

SOURCE = "report"
SYSTEM = Actor(name="report service", roles=["service"])


async def drafted(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any],
    session: AsyncClientSession,
) -> Envelope:
    """The first draft PDF is ready (PRD RPT-1). Keyed by the request (TRD 8.1)."""
    visit = report["content"]["facts"]["visit"]
    data = ev.ReportDrafted(
        report_id=report["_id"], number=report["number"], version=report["version"],
        visit_id=report["visit_id"], request_id=report["request_id"],
        request_ref=visit["request_ref"], org_id=report["org_id"], title=visit.get("request_title"),
        staff_ids=list(report["staff_ids"]), lead_staff_id=report["lead_staff_id"],
    )
    envelope = Envelope(
        event_id=new_id(), type="report.drafted", occurred_at=clock.now(), source=SOURCE,
        key=report["request_id"], aggregate_version=report["version"], actor=SYSTEM,
        org_id=report["org_id"], resource=Resource(type="report", id=report["_id"]),
        data=data.model_dump(mode="json"),
    )
    await outbox.add(db["outbox"], envelope, session=session, clock=clock)
    return envelope
