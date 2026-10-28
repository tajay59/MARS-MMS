"""`render_closeout` (PRD RPT-8, RPT-6; TRD 11.1; W18-11, W18-12): draw a request's close-out
report and store the PDF. Job id `closeout:<report id>`.

`tick` (about every half minute, under a Redis lock) queues the close-outs `request.closed` and a
correction made, and draws again one that failed an hour ago (nobody can try again for it). The job
reads the facts from operations. If the record was made for a corrected visit report operations
does not yet know (`expects`), it waits up to five minutes for it. It draws the page, stores
`closeouts/<report id>/final.pdf` and, in ONE transaction, makes the report `final`, makes the
version it replaces `superseded` and adds `report.closeout_generated`. If another correction joined
the record while the facts were being read (`inputs_seq`), the draw is thrown away and done again.
Safe to repeat: a finished report is not claimed.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import closeout, closeout_view
from app.events import publish
from app.jobs.labels import Retry
from app.jobs.render_draft import CONTENT_TYPE
from app.repo import reports
from app.services import Services

log = get_logger(__name__)

WAIT_S = 300  # how long a corrected report is waited for before the close-out is drawn without it
WAIT_RETRY_S = 30
FAILED_RETRY_S = 3600


def job_id(report_id: str) -> str:
    return f"closeout:{report_id}"


async def tick(svc: Services) -> dict[str, int]:
    """Queue the close-outs nobody has queued, or whose worker is gone; start the failed ones
    again. Returns what it did."""
    now = svc.clock.now()
    stuck = now - timedelta(seconds=svc.settings.finalizing_timeout_s)
    restarted = await reports.restart_failed_closeouts(
        svc.db, now - timedelta(seconds=FAILED_RETRY_S), now)
    queued = 0
    for report in await reports.rendering_waiting(svc.db, closeout.TYPE, stuck):
        if await reports.queue_rendering(svc.db, report["_id"], now, stuck):
            await svc.jobs.enqueue(job_id(report["_id"]))
            queued += 1
    return {"queued": queued, "restarted": len(restarted)}


async def _fail(svc: Services, report: dict[str, Any], code: str) -> None:
    async def save(session: AsyncClientSession) -> None:
        await reports.fail_closeout(
            svc.db, report["_id"], code=code, now=svc.clock.now(), session=session)

    await in_transaction(svc.client, save)


def _waited_enough(svc: Services, report: dict[str, Any]) -> bool:
    queued = report["render"].get("queued_at")
    return queued is None or svc.clock.now() - queued >= timedelta(seconds=WAIT_S)


async def render_closeout(svc: Services, report_id: str) -> None:
    report = await reports.claim_rendering(svc.db, report_id, svc.clock.now())
    if report is None:
        return  # done, failed or unknown: nothing to do
    try:
        facts = await svc.facts.closeout_facts(report["request_id"])
        if facts is None:
            raise LookupError("operations does not know the request")
        if closeout.not_yet_known(report["expects"], facts) and not _waited_enough(svc, report):
            # Operations has not taken in the corrected report yet: look again shortly
            await reports.requeue_rendering(svc.db, report_id, svc.clock.now(), waiting=True)
            raise Retry(WAIT_RETRY_S)
        previous = (
            await reports.get(svc.db, report["supersedes_id"]) if report["supersedes_id"] else None)
        before = (previous or {}).get("content", {}).get("closeout")
        digest = closeout.content_hash(facts)
        now = svc.clock.now()
        found = [*(previous or {}).get("corrections", []),
                 *closeout.corrections(before, facts, now)]
        view = closeout_view.build(
            {**report, "content_hash": digest}, facts, app_url=svc.settings.app_url,
            generated_at=now, corrections=found)
        rendered = await svc.renderer.closeout(view, report["template_version"])
        key = closeout.final_key(report_id)
        await svc.storage.put(svc.settings.bucket_reports, key, rendered.pdf, CONTENT_TYPE)
    except Retry:
        raise
    except Exception as e:  # noqa: BLE001 - any failure to draw is a failed try
        if report["render"]["attempts"] >= svc.settings.job_max_attempts:
            log.error("closeout_failed", report_id=report_id, reason=type(e).__name__)
            await _fail(svc, report, "render_failed")
            return
        await reports.requeue_rendering(svc.db, report_id, svc.clock.now())
        log.warning("closeout_retry", report_id=report_id, reason=type(e).__name__,
                    attempts=report["render"]["attempts"])
        raise Retry from e

    pdf = {
        "key": key, "sha256": hashlib.sha256(rendered.pdf).hexdigest(), "bytes": len(rendered.pdf),
        "pages": rendered.pages, "template_version": report["template_version"],
        "at": svc.clock.now(),
    }

    async def save(session: AsyncClientSession) -> bool:
        if not await reports.finish_closeout(
            svc.db, report_id, inputs_seq=report["inputs_seq"], facts=closeout.kept_facts(facts),
            content_hash=digest, final_pdf=pdf, corrections=found, session=session,
        ):
            return False
        if previous is not None:
            await reports.supersede(
                svc.db, previous["_id"], by="system", now=svc.clock.now(), session=session)
        await publish.closeout_generated(
            svc.db, svc.clock, {**report, "final_pdf": pdf}, session=session)
        return True

    if not await in_transaction(svc.client, save):
        # A correction joined while this was drawn (or it was finished elsewhere): look again
        await reports.release_rendering(svc.db, report_id, svc.clock.now())
