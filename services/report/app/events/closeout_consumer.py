"""A request's close-out report from operations' `request.closed` (PRD RPT-8; TRD 3.4 "Consumes";
W18-11), and the correction of a visit report after the request closed (RPT-6; W18-12).

`request.closed` makes the record at once, in the consumer's transaction: its number, its state,
nothing drawn. The facts are read from operations afterwards (`jobs/render_closeout.py`), because an
HTTP call has no place inside a Mongo transaction and events never carry the client's drawing. A
repeat of the event changes nothing.

A visit report that becomes final as a version 2 or later is handled where it becomes final
(`on_visit_report_final`, called in that transaction): it makes close-out version n + 1, or joins
the close-out that is still to be drawn, or does nothing when the request has no close-out yet.
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

from app.domain import closeout
from app.repo import reports

TOPICS = ["mms.operations.events"]


async def on_visit_report_final(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any],
    session: AsyncClientSession,
) -> str:
    """A visit report just became final. Returns what happened to the close-out: `skip`, `merge`
    or `new` (the decision tree of `closeout.decide_version`)."""
    now = clock.now()
    latest = await reports.latest_closeout(db, report["request_id"], session)
    what = closeout.decide_version(latest, visit_version=report["version"])
    if latest is None or what == "skip":
        return what
    if what == "merge":
        await reports.merge_expectation(
            db, latest["_id"], report["visit_id"], report["version"], now, session)
        return what
    await reports.insert_if_new(db, closeout.new_closeout(
        report_id=new_id(), request_id=report["request_id"], request_ref=latest["request_ref"],
        title=latest.get("title"), org_id=latest["org_id"], version=latest["version"] + 1,
        supersedes_id=latest["_id"], expects={report["visit_id"]: report["version"]}, now=now,
    ), session)
    return what


def handlers(db: AsyncDatabase[dict[str, Any]], clock: Clock) -> dict[str, Handler]:
    async def closed(payload: BaseModel, envelope: Envelope, session: AsyncClientSession) -> None:
        if not isinstance(payload, ops_ev.RequestClosed):  # pragma: no cover
            raise TypeError(type(payload).__name__)
        if await reports.latest_closeout(db, payload.request_id, session) is not None:
            return
        await reports.insert_if_new(db, closeout.new_closeout(
            report_id=new_id(), request_id=payload.request_id, request_ref=payload.ref,
            title=payload.title, org_id=payload.org_id, version=1, supersedes_id=None,
            expects={}, now=clock.now(),
        ), session)

    return {"request.closed": closed}
