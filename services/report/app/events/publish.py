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


def _visit(report: dict[str, Any]) -> dict[str, Any]:
    visit: dict[str, Any] = report["content"]["facts"]["visit"]
    return visit


async def finalized(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *, finalized_by: str,
    pdf_sha256: str, at: Any, actor: Actor, session: AsyncClientSession,
) -> Envelope:
    """The visit report is final (RPT-4, RPT-5). Operations sets the visit's report status from
    this and platform tells the people concerned."""
    visit = _visit(report)
    data = ev.ReportFinalized(
        **_about(report), subject_ref=report["subject_ref"], request_ref=visit["request_ref"],
        title=visit.get("request_title"), staff_ids=list(report["staff_ids"]),
        lead_staff_id=report["lead_staff_id"], finalized_at=at,
        finalized_by=finalized_by, pdf_sha256=pdf_sha256,
    )
    return await _add(db, clock, report, "report.finalized", data, actor, session)


async def finalize_failed(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *, reason: str,
    attempts: int, signer_ids: list[str], session: AsyncClientSession,
) -> Envelope:
    """Finalizing stopped and the report is a draft again (TRD 11.2)."""
    visit = _visit(report)
    data = ev.ReportFinalizeFailed(
        **_about(report), reason=reason, attempts=attempts,  # type: ignore[arg-type]
        request_ref=visit["request_ref"], title=visit.get("request_title"),
        lead_staff_id=report["lead_staff_id"], signer_ids=signer_ids,
    )
    return await _add(db, clock, report, "report.finalize_failed", data, SYSTEM, session)


async def finalize_reminder(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *,
    working_days: int, staff_ids: list[str], session: AsyncClientSession,
) -> Envelope:
    """A draft is still not final after 2 or 5 working days (PRD RPT-7)."""
    visit = _visit(report)
    data = ev.ReportFinalizeReminder(
        **_about(report), working_days=working_days,  # type: ignore[arg-type]
        request_ref=visit["request_ref"], title=visit.get("request_title"),
        staff_ids=staff_ids, lead_staff_id=report["lead_staff_id"],
    )
    return await _add(db, clock, report, "report.finalize_reminder", data, SYSTEM, session)


async def reopened(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *,
    previous_version: int, reason: str, reopened_by: str, request_status: str | None,
    actor: Actor, session: AsyncClientSession,
) -> Envelope:
    """An admin reopened a final report (RPT-6). `report` is the new draft."""
    visit = _visit(report)
    data = ev.ReportReopened(
        **_about(report), previous_version=previous_version, reason=reason,
        reopened_by=reopened_by, request_ref=visit["request_ref"], title=visit.get("request_title"),
        staff_ids=list(report["staff_ids"]), lead_staff_id=report["lead_staff_id"],
        request_status=request_status,
    )
    return await _add(db, clock, report, "report.reopened", data, actor, session)
