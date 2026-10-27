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


def _about(report: dict[str, Any]) -> dict[str, Any]:
    """What every event about one version of a visit report names."""
    return {
        "report_id": report["_id"], "number": report["number"], "version": report["version"],
        "visit_id": report["visit_id"], "request_id": report["request_id"],
        "org_id": report["org_id"],
    }


async def _add(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], type_: str,
    data: Any, actor: Actor, session: AsyncClientSession,
) -> Envelope:
    envelope = Envelope(
        event_id=new_id(), type=type_, occurred_at=clock.now(), source=SOURCE,
        key=report["request_id"], aggregate_version=report["version"], actor=actor,
        org_id=report["org_id"], resource=Resource(type="report", id=report["_id"]),
        data=data.model_dump(mode="json"),
    )
    await outbox.add(db["outbox"], envelope, session=session, clock=clock)
    return envelope


async def signed(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *, signer_id: str,
    role: str, valid_signatures: int, actor: Actor, session: AsyncClientSession,
) -> Envelope:
    """A member of the visit signed the draft (RPT-4). Ids and counts only: never the drawing or
    the typed name."""
    data = ev.ReportSigned(
        **_about(report), signer_id=signer_id, role=role,  # type: ignore[arg-type]
        content_version=report["content_version"], valid_signatures=valid_signatures,
    )
    return await _add(db, clock, report, "report.signed", data, actor, session)


async def signatures_cleared(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *, count: int,
    reason: str, actor: Actor, session: AsyncClientSession,
) -> Envelope:
    """The draft changed after it was signed (TRD 11.2 step 3)."""
    data = ev.ReportSignaturesCleared(
        **_about(report), count=count, reason=reason,  # type: ignore[arg-type]
    )
    return await _add(db, clock, report, "report.signatures_cleared", data, actor, session)
