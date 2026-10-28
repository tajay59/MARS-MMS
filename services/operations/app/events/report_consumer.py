"""The report service's events on a visit report (`mms.report.events`, TRD §3.2 "Consumes").

`report.finalized` makes the visit's report final and `report.reopened` makes it a draft again;
either can move the request into or out of Client Review, so the request is settled in the same
transaction as the visit (ADR-17, rule 2). The report's version guards the write: an event older
than what the visit already knows changes nothing. Other report events (`report.drafted`, the
signing events) are not operations' business and are ignored. `report.generated` is the PDF of a
client's online-form report (W18-10): it says the report is ready, or could not be drawn.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import Handler
from mms_common.events import Actor, Envelope
from mms_common.events import report as report_ev
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import client_reports as client_report_rules
from app.domain.visits import lock as rules
from app.events.publish import Emitter
from app.events.settle import lock_request, settle_request
from app.repo import client_reports as client_report_repo
from app.repo.visits import visits as visit_repo

TOPICS = ["mms.report.events"]
SYSTEM = Actor(roles=["service"], name="report")


def handlers(db: AsyncDatabase[dict[str, Any]], clock: Clock) -> dict[str, Handler]:
    emitter = Emitter(db, clock, SYSTEM, None)

    async def apply(
        visit_id: str, changes_of: Any, note: str, session: AsyncClientSession
    ) -> None:
        visit = await visit_repo.get(db, visit_id, None, session)
        if visit is None:
            return  # a visit this copy never had (an old event after a restore): nothing to do
        changes = changes_of(visit)
        if not changes:
            return
        request = await lock_request(db, visit["request_id"], session)
        await visit_repo.update(db, visit_id, changes, now=clock.now(), by=None, session=session)
        await settle_request(db, clock, emitter, request, session, by=None, by_name=None,
                             note=f"{note} ({visit['ref']})")

    async def finalized(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        if not isinstance(payload, report_ev.ReportFinalized):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        await apply(
            payload.visit_id,
            lambda v: rules.finalized(v, payload.report_id, payload.version, payload.finalized_at),
            f"Visit report v{payload.version} final", session,
        )

    async def reopened(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        if not isinstance(payload, report_ev.ReportReopened):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        await apply(
            payload.visit_id,
            lambda v: rules.reopened(v, payload.report_id, payload.version),
            f"Visit report reopened as v{payload.version}", session,
        )

    async def generated(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        """Record where a form report's PDF stands. Only the answer to the latest submission
        counts, and only once: a repeat, or the answer to an earlier try, changes nothing."""
        if not isinstance(payload, report_ev.ReportGenerated):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        doc = await client_report_repo.get(db, payload.client_report_id, None, session)
        if (doc is None or doc["attempt"] != payload.attempt
                or doc["render"] != client_report_rules.Render.RENDERING.value):
            return
        ready = payload.outcome == "ready"
        await client_report_repo.update(
            db, doc["_id"],
            {"render": (client_report_rules.Render.READY if ready
                        else client_report_rules.Render.FAILED).value,
             "report_id": payload.report_id},
            now=clock.now(), by=None, expected_version=None, session=session,
        )

    return {
        "report.finalized": finalized, "report.reopened": reopened, "report.generated": generated,
    }
