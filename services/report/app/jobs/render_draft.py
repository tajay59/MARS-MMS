"""`render_draft` (TRD 11.1, 11.2; W16-5 to W16-7): draw a visit report draft and store the PDF.

The report says what it holds (`content`, at its `content_version` and `facts_version`); the job
renders exactly that, stores `visits/<report id>/draft-<cv>-<fv>.pdf` and records it. The first
PDF of a visit also emits `report.drafted` in the same transaction. If the report moved on while
the job ran, the PDF is stored but not current, and a preview asks for a new one. Safe to repeat:
the key is a function of the versions, and a finished render is not claimed again.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import visit_view
from app.events import publish
from app.jobs.labels import Retry
from app.repo import reports
from app.repo.operations import OperationsUnavailable
from app.repo.render import jpeg_data_uri
from app.repo.storage import StorageError
from app.services import Services

log = get_logger(__name__)

CONTENT_TYPE = "application/pdf"
PICTURES_AT_ONCE = 4


def object_key(report_id: str, content_version: int, facts_version: int) -> str:
    return f"visits/{report_id}/draft-{content_version}-{facts_version}.pdf"


async def _pictures(svc: Services, report: dict[str, Any]) -> dict[str, str | None]:
    """Each selected photo's display copy as a page-sized JPEG; None when it cannot be had (the
    page prints a grey box and its caption)."""
    ids = list(dict.fromkeys(s["media_id"] for s in report["content"]["media_selection"]))
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

    return dict(await asyncio.gather(*(one(i) for i in ids)))


async def render_draft(svc: Services, report_id: str) -> None:
    now = svc.clock.now()
    report = await reports.claim_render(svc.db, report_id, now)
    if report is None:
        return  # not a draft, already done, or unknown: nothing to do
    cv, fv = report["content_version"], report["facts_version"]
    try:
        pictures = await _pictures(svc, report)
        view = visit_view.build(report, pictures, app_url=svc.settings.app_url, generated_at=now)
        rendered = await svc.renderer.visit_report(view, report["template_version"])
        key = object_key(report_id, cv, fv)
        await svc.storage.put(svc.settings.bucket_reports, key, rendered.pdf, CONTENT_TYPE)
    except (OperationsUnavailable, StorageError) as e:
        if report["render"]["attempts"] >= svc.settings.job_max_attempts:
            log.error("draft_failed", report_id=report_id, reason=type(e).__name__)
            await reports.fail_render(svc.db, report_id, "unavailable", svc.clock.now())
            return
        await reports.requeue_render(svc.db, report_id, svc.clock.now())
        raise Retry from e
    except Exception:
        log.exception("draft_render_failed", report_id=report_id)
        await reports.fail_render(svc.db, report_id, "render_failed", svc.clock.now())
        return

    first = report.get("draft_pdf") is None
    pdf = {
        "key": key, "sha256": hashlib.sha256(rendered.pdf).hexdigest(), "bytes": len(rendered.pdf),
        "pages": rendered.pages, "content_version": cv, "facts_version": fv,
        "template_version": report["template_version"], "at": svc.clock.now(),
    }

    async def save(session: AsyncClientSession) -> bool:
        stored = await reports.finish_render(svc.db, report_id, pdf, first=first, session=session)
        if stored and first:
            await publish.drafted(svc.db, svc.clock, report, session)
        return stored

    if not await in_transaction(svc.client, save):
        return  # the report left draft meanwhile (W17: finalized); the PDF is not used
    previous = report.get("draft_pdf")
    if previous and previous["key"] != key:
        try:
            await svc.storage.delete(svc.settings.bucket_reports, previous["key"])
        except StorageError:
            log.warning("old_draft_not_deleted", report_id=report_id)
