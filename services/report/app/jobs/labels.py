"""`render_labels` (TRD §9): fetch the stations from operations, draw the sheets, store the
PDF. Safe to repeat: the object key is the job's, and a finished job is not run again."""

from __future__ import annotations

import hashlib
from typing import Any

from mms_common.logging import get_logger

from app.domain import labels as rules
from app.domain.labels import Label
from app.repo import jobs
from app.repo.operations import OperationsUnavailable
from app.repo.storage import StorageError
from app.services import Services

log = get_logger(__name__)

CONTENT_TYPE = "application/pdf"


class Retry(Exception):  # noqa: N818 - reads as the instruction it is
    """A dependency was unreachable: the worker runs the job again later."""


def object_key(job_id: str) -> str:
    return f"labels/{job_id}.pdf"


async def render_labels(svc: Services, job_id: str) -> None:
    now = svc.clock.now()
    job = await jobs.claim(svc.db, job_id, now)
    if job is None:
        return  # done, failed or unknown: nothing to do
    params: dict[str, Any] = job["params"]
    ids: list[str] = params["station_ids"]
    try:
        found = await svc.stations.labels(ids, job.get("request_id"))
        if not found:
            await jobs.fail(svc.db, job_id, "no_stations", svc.clock.now())
            return
        sheet = [
            Label(
                station_id=s.station_id, code=s.code, name=s.name, org_name=s.org_name,
                scan_url=rules.scan_url(svc.settings.app_url, s.qr_token),
            )
            for s in found
        ]
        rendered = await svc.renderer.labels(sheet, params.get("contact_phone"))
        key = object_key(job_id)
        await svc.storage.put(svc.settings.bucket_reports, key, rendered.pdf, CONTENT_TYPE)
    except (OperationsUnavailable, StorageError) as e:
        if job["attempts"] >= svc.settings.job_max_attempts:
            log.error("labels_failed", job_id=job_id, reason=type(e).__name__)
            await jobs.fail(svc.db, job_id, "unavailable", svc.clock.now())
            return
        await jobs.requeue(svc.db, job_id, svc.clock.now())
        raise Retry from e
    except Exception:
        log.exception("labels_render_failed", job_id=job_id)
        await jobs.fail(svc.db, job_id, "render_failed", svc.clock.now())
        return
    shown = {s.station_id for s in found}
    await jobs.finish(svc.db, job_id, {
        "pdf_key": key,
        "pdf_sha256": hashlib.sha256(rendered.pdf).hexdigest(),
        "pdf_bytes": len(rendered.pdf),
        "pages": rendered.pages,
        "template_version": rules.TEMPLATE_VERSION,
        "stations": len(found),
        "missing": [i for i in dict.fromkeys(ids) if i not in shown],
    }, svc.clock.now())
