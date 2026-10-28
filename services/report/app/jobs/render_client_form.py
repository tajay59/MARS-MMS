"""`render_client_form` (PRD CRP-3; TRD 11.1; W18-10): draw a client's online-form report and
store the PDF. Job id `clientform:<report id>`.

`tick` (about every half minute, under a Redis lock) queues the reports `client_report.submitted`
made. The job reads the text and the list of pictures from operations, draws the page, stores
`client-forms/<report id>/final-<attempt>.pdf` and, in ONE transaction, makes the report `final`
and adds `report.generated`. A try that fails (operations down, the store, the renderer) is
repeated up to `job_max_attempts` times; the last failure marks the report `render_failed` and
tells operations, so the client may try again. Safe to repeat: a finished report is not claimed,
and the transaction only lands once for the attempt it drew.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from typing import Any

from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import client_form, client_form_view
from app.events import publish
from app.jobs.labels import Retry
from app.jobs.render_draft import CONTENT_TYPE
from app.repo import reports
from app.repo.render import jpeg_data_uri
from app.services import Services

log = get_logger(__name__)

PICTURES_AT_ONCE = 4


def job_id(report_id: str) -> str:
    return f"clientform:{report_id}"


async def tick(svc: Services) -> dict[str, int]:
    """Queue the forms nobody has queued, or whose worker is gone. Returns what it did."""
    now = svc.clock.now()
    stuck = now - timedelta(seconds=svc.settings.finalizing_timeout_s)
    queued = 0
    for report in await reports.rendering_waiting(svc.db, "client_form", stuck):
        if await reports.queue_rendering(svc.db, report["_id"], now, stuck):
            await svc.jobs.enqueue(job_id(report["_id"]))
            queued += 1
    return {"queued": queued}


async def _pictures(svc: Services, facts: dict[str, Any]) -> dict[str, str | None]:
    """Each picture as a page-sized JPEG; None when it cannot be had (the page says so)."""
    gate = asyncio.Semaphore(PICTURES_AT_ONCE)

    async def one(media_id: str) -> tuple[str, str | None]:
        async with gate:
            raw = await svc.media.rendition(media_id)
            if raw is None:
                return media_id, None
            try:
                return media_id, await asyncio.to_thread(jpeg_data_uri, raw)
            except Exception:  # noqa: BLE001 - one unreadable picture must not stop the report
                log.warning("picture_unreadable", media_id=media_id)
                return media_id, None

    ids = list(dict.fromkeys(i["media_id"] for i in facts["images"]))
    return dict(await asyncio.gather(*(one(i) for i in ids)))


async def _fail(svc: Services, report: dict[str, Any], code: str) -> None:
    """The last try failed: the report says so, and so does the event operations waits for."""

    async def save(session: AsyncClientSession) -> None:
        if await reports.fail_client_form(
            svc.db, report["_id"], attempt=report["attempt"], code=code, now=svc.clock.now(),
            session=session,
        ):
            await publish.generated(svc.db, svc.clock, report, outcome="failed", session=session)

    await in_transaction(svc.client, save)


async def render_client_form(svc: Services, report_id: str) -> None:
    report = await reports.claim_rendering(svc.db, report_id, svc.clock.now())
    if report is None:
        return  # done, failed or unknown: nothing to do
    attempt = report["attempt"]
    try:
        facts = await svc.facts.client_report_facts(report["client_report_id"])
        if facts is None:
            log.error("client_form_unknown", report_id=report_id)
            await _fail(svc, report, "unknown_report")
            return
        pictures = await _pictures(svc, facts)
        digest = client_form.content_hash(facts)
        view = client_form_view.build(
            {**report, "content_hash": digest}, facts, pictures, generated_at=svc.clock.now())
        rendered = await svc.renderer.client_form(view, report["template_version"])
        key = client_form.final_key(report_id, attempt)
        await svc.storage.put(svc.settings.bucket_reports, key, rendered.pdf, CONTENT_TYPE)
    except Exception as e:  # noqa: BLE001 - any failure to draw is a failed try
        if report["render"]["attempts"] >= svc.settings.job_max_attempts:
            log.error("client_form_failed", report_id=report_id, reason=type(e).__name__)
            await _fail(svc, report, "render_failed")
            return
        await reports.requeue_rendering(svc.db, report_id, svc.clock.now())
        log.warning("client_form_retry", report_id=report_id, reason=type(e).__name__,
                    attempts=report["render"]["attempts"])
        raise Retry from e

    pdf = {
        "key": key, "sha256": hashlib.sha256(rendered.pdf).hexdigest(), "bytes": len(rendered.pdf),
        "pages": rendered.pages, "template_version": report["template_version"],
        "at": svc.clock.now(),
    }

    async def save(session: AsyncClientSession) -> None:
        if await reports.finish_client_form(
            svc.db, report_id, attempt=attempt, facts=facts, content_hash=digest, final_pdf=pdf,
            session=session,
        ):
            await publish.generated(
                svc.db, svc.clock, {**report, "final_pdf": pdf}, outcome="ready", session=session)

    await in_transaction(svc.client, save)
