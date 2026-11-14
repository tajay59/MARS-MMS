"""`finalize` (TRD 11.2 steps 4 and 4.5; PRD RPT-4, RPT-5; W17-7): the saga that turns a signed
draft into a final report. Job id `finalize:<report id>`; safe to repeat at every step.

    1. the report is `finalizing` (the route did that) and the job counts a try;
    2. the visit is locked for this report version (operations, idempotent);
    3. the facts are read again; if what prints changed, the signatures are cleared and the report
       is a draft again (`facts_changed`);
    4. the final PDF is drawn and stored, and in ONE transaction the report becomes `final` and
       `report.finalized` goes to the outbox.

Drawing is tried `finalize_retries` times with a growing wait. When the last try fails the report
is a draft again with its signatures (the content did not change), `finalize_error` says why,
the visit is unlocked and `report.finalize_failed` goes to the lead. The unlock is owed to
operations in the same transaction (`unlock_pending`) and done right after; the cron does it if
that call fails. A job that dies is taken up again by `jobs/resume.py`.
"""

from __future__ import annotations

import hashlib
from typing import Any

from mms_common.events import Actor
from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import content as content_rules
from app.domain import drafts, finalize, visit_view
from app.events import closeout_consumer, publish
from app.events import signatures as sign_events
from app.jobs.labels import Retry
from app.jobs.render_draft import CONTENT_TYPE, pictures_for
from app.repo import reports, signatures
from app.repo.operations import LockRefused, OperationsUnavailable
from app.services import Services

log = get_logger(__name__)


def job_id(report_id: str) -> str:
    return f"finalize:{report_id}"


async def release_lock(svc: Services, report: dict[str, Any]) -> None:
    """Open the visit's boards again. If operations does not answer, `unlock_pending` stays on
    the report and the cron comes back to it."""
    pending = report.get("unlock_pending")
    if not pending:
        return
    try:
        await svc.locks.unlock(report["visit_id"], pending["report_id"], pending["version"])
    except OperationsUnavailable:
        log.warning("unlock_owed", report_id=report["_id"])
        return
    except LockRefused:
        pass  # the visit is gone or someone else holds it: nothing of ours to open
    await reports.clear_unlock(svc.db, report["_id"], pending)


async def _stop(
    svc: Services, report: dict[str, Any], reason: str, *, clear: bool = False, stale: bool = False
) -> None:
    """Back to a draft: the error is stored, the lead is told, the unlock is owed. `clear` also
    clears the signatures (what prints changed)."""
    signed = await signatures.valid(svc.db, report["_id"], report["version"])
    owed = {"report_id": report["_id"], "version": report["version"]}

    async def save(session: AsyncClientSession) -> None:
        if not await reports.back_to_draft(
            svc.db, report["_id"], error=reason, stale=stale, unlock=owed,
            now=svc.clock.now(), session=session,
        ):
            return
        if clear:
            await sign_events.clear(
                svc.db, svc.clock, report, reason="facts", by="facts", actor=publish.SYSTEM,
                session=session)
        await publish.finalize_failed(
            svc.db, svc.clock, report, reason=reason, attempts=report["finalize_attempts"],
            signer_ids=[s["signer_id"] for s in signed], session=session)

    await in_transaction(svc.client, save)
    log.warning("finalize_stopped", report_id=report["_id"], reason=reason)
    await release_lock(svc, {**report, "unlock_pending": owed})


def _try_again(svc: Services, report: dict[str, Any], error: Exception) -> Retry:
    wait = finalize.backoff(report["finalize_attempts"], svc.settings.finalize_backoff_s)
    log.warning("finalize_retry", report_id=report["_id"], reason=type(error).__name__,
                attempts=report["finalize_attempts"])
    return Retry(wait)


async def finalize_report(svc: Services, report_id: str) -> None:
    report = await reports.claim_finalizing(svc.db, report_id, svc.clock.now())
    if report is None:
        return  # not finalizing (done, stopped or unknown): nothing to do
    version, visit_id = report["version"], report["visit_id"]
    last = finalize.out_of_tries(report["finalize_attempts"], svc.settings.finalize_retries)

    # 2. Lock the visit's boards for this version
    try:
        await svc.locks.lock(visit_id, report_id, version)
    except LockRefused:
        await _stop(svc, report, "lock_failed")
        return
    except OperationsUnavailable as e:
        if last:
            await _stop(svc, report, "lock_failed")
            return
        raise _try_again(svc, report, e) from e

    # 3. The facts as they are now, with the boards locked: do they print what was signed?
    try:
        facts = await svc.facts.visit_facts(visit_id)
    except OperationsUnavailable as e:
        if last:
            await _stop(svc, report, "lock_failed")
            return
        raise _try_again(svc, report, e) from e
    if facts is None:
        await _stop(svc, report, "lock_failed")
        return
    content = report["content"]
    now_hash = content_rules.content_hash({
        "facts": facts, "narrative": content["narrative"],
        "media_selection": drafts.refreshed_selection(content["media_selection"], facts),
    })
    if now_hash != report["content_hash"]:
        await _stop(svc, report, "facts_changed", clear=True, stale=True)
        return

    # 4. Draw the final PDF and make the report final
    signed = await signatures.valid(svc.db, report_id, version)
    if finalize.lead_signature(signed, report) is None:  # cannot happen; never finalize unsigned
        await _stop(svc, report, "render_failed")
        return
    try:
        pictures = await pictures_for(svc, report)
        view = visit_view.build(
            report, pictures, app_url=svc.settings.app_url, generated_at=svc.clock.now(),
            signatures=signed)
        rendered = await svc.renderer.visit_report(view, report["template_version"])
        key = finalize.final_key(report_id, version)
        await svc.storage.put(svc.settings.bucket_reports, key, rendered.pdf, CONTENT_TYPE)
    except Exception as e:  # noqa: BLE001 - any failure to draw is a failed try
        if last:
            log.error("finalize_render_failed", report_id=report_id, reason=type(e).__name__)
            await _stop(svc, report, "render_failed")
            return
        raise _try_again(svc, report, e) from e

    at = svc.clock.now()
    pdf = {
        "key": key, "sha256": hashlib.sha256(rendered.pdf).hexdigest(), "bytes": len(rendered.pdf),
        "pages": rendered.pages, "template_version": report["template_version"], "at": at,
    }
    by = report["finalize_requested_by"]
    actor = Actor(**report["finalize_actor"])

    async def save(session: AsyncClientSession) -> None:
        if await reports.finish_final(
            svc.db, report_id, final_pdf=pdf, by=by, at=at, content_hash=report["content_hash"],
            session=session,
        ):
            await publish.finalized(
                svc.db, svc.clock, report, finalized_by=by, pdf_sha256=pdf["sha256"],
                at=at, actor=actor, session=session)
            # A correction after the request closed makes the next close-out version (W18-12)
            await closeout_consumer.on_visit_report_final(svc.db, svc.clock, report, session)

    await in_transaction(svc.client, save)

