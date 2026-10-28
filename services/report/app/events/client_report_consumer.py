"""A client's online-form report from operations' `client_report.submitted` (PRD CRP-3; TRD 3.4
"Consumes"; W18-10).

The event makes the report record at once, in the consumer's transaction: its number, its
state, nothing drawn. The text is read from operations afterwards (`jobs/render_client_form.py`),
because an HTTP call has no place inside a Mongo transaction and events never carry text. A
repeat of the event changes nothing; a later attempt on a report whose PDF failed starts it
again. A report that is only a PDF upload is operations' alone.
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import Handler
from mms_common.events import Envelope
from mms_common.events import operations as ops_ev
from mms_common.ids import new_id
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import client_form
from app.repo import reports

TOPICS = ["mms.operations.events"]


def handlers(db: AsyncDatabase[dict[str, Any]], clock: Clock) -> dict[str, Handler]:
    async def submitted(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        if not isinstance(payload, ops_ev.ClientReportSubmitted):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        if payload.kind != "form":
            return
        now = clock.now()
        existing = await reports.for_client_report(db, payload.client_report_id, session)
        if existing is not None:
            if client_form.can_try_again(existing, payload.attempt):
                await reports.restart_client_form(
                    db, existing["_id"], attempt=payload.attempt, now=now, session=session)
            return
        sequence = await reports.next_sequence(
            db, client_form.counter_key(payload.request_id), session)
        await reports.insert_if_new(db, client_form.new_report(
            report_id=new_id(), client_report_id=payload.client_report_id,
            report_number=client_form.number(payload.ref, sequence),
            request_id=payload.request_id, org_id=payload.org_id,
            submitted_by=payload.submitted_by_id, attempt=payload.attempt, now=now,
        ), session)

    return {"client_report.submitted": submitted}
