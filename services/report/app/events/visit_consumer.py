"""Visit reports from operations' visit events (TRD 3.4 "Consumes", 11.2; PRD RPT-1; W16-1, W16-4).

- `visit.ended` makes the draft report: a record only, in the consumer's transaction. Its facts
  are read from operations afterwards (`jobs/drafts.py`), because an HTTP call has no place
  inside a Mongo transaction.
- `visit.element_*` for a visit whose report is a draft marks the facts stale, so they are read
  again. The event says a board changed and carries no text; the narrative is never touched.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import Handler
from mms_common.events import Envelope
from mms_common.ids import new_id
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import drafts, numbering
from app.repo import reports

TOPICS = ["mms.operations.events"]


def handlers(db: AsyncDatabase[dict[str, Any]], clock: Clock) -> dict[str, Handler]:
    async def ended(payload: BaseModel, envelope: Envelope, session: AsyncClientSession) -> None:
        data = payload.model_dump()
        now = clock.now()
        doc = drafts.new_draft(
            report_id=new_id(), number=numbering.visit_report_number(data["ref"]),
            subject_ref=f"visit:{data['visit_id']}", visit_id=data["visit_id"],
            request_id=data["request_id"], org_id=data["org_id"],
            staff_ids=list(data["staff_ids"]), lead_staff_id=data["lead_staff_id"],
            ended_at=data["ended_at"], now=now,
        )
        await reports.insert_if_new(db, doc, session)

    async def board_changed(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        await reports.mark_stale(db, payload.model_dump()["visit_id"], clock.now(), session)

    return {
        "visit.ended": ended,
        "visit.element_added": board_changed,
        "visit.element_updated": board_changed,
        "visit.element_deleted": board_changed,
    }
