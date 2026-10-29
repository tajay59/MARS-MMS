"""`render_summary` (TRD 9, 11.1; W19-8): read the rows, build the tables, write the CSV or draw
the PDF, store it. Safe to repeat: the object key is the job's, and a finished job is not run
again. Also the clean-up that removes a summary after `REPORT_SUMMARY_KEEP_DAYS`."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from mms_common import safecsv
from mms_common.errors import NotFound
from mms_common.logging import get_logger

from app.domain import charts, summary
from app.domain.labels import JobType
from app.domain.summary import TEMPLATE_VERSION, Kind
from app.jobs.labels import Retry
from app.repo import jobs
from app.repo import summary as data_repo
from app.repo.storage import StorageError
from app.services import Services

log = get_logger(__name__)

CONTENT_TYPES = {"pdf": "application/pdf", "csv": "text/csv; charset=utf-8"}


def object_key(job_id: str, fmt: str) -> str:
    return f"summaries/{job_id}.{fmt}"


def filters_text(params: dict[str, Any], stations: int, zone: str, kind: Kind,
                 p: summary.Period | None, today: date) -> str:
    """The filters as a line under the title, so a printed report says what it covers."""
    when = (f"{p.from_date.isoformat()} to {p.to_date.isoformat()}" if p
            else f"as of {today.isoformat()}")
    org = "one organization" if params.get("org_id") else "all organizations"
    country = params.get("country") or "all countries"
    return f"{when} · {org} · {country} · {stations} stations · times in {zone}"


async def render_summary(svc: Services, job_id: str) -> None:
    job = await jobs.claim(svc.db, job_id, svc.clock.now())
    if job is None:
        return
    params: dict[str, Any] = job["params"]
    fmt: str = params["format"]
    zone = svc.settings.summary_time_zone
    try:
        kind = Kind(params["type"])
        p = None
        if summary.TYPES[kind].uses_period:
            p = summary.period(date.fromisoformat(params["from"]), date.fromisoformat(params["to"]),
                               zone, svc.settings.summary_max_days)
        scope, stations = await data_repo.resolve(
            svc.db, org_id=params.get("org_id"), country=params.get("country"),
            station_ids=params.get("station_ids"))
        now = svc.clock.now()
        data = await data_repo.fetch(
            svc.db, kind, scope, stations, p, now=now,
            due_in_days=int(params.get("due_in_days") or 30), zone=zone)
        doc = summary.build(kind, data)
        if fmt == "csv":
            body = "".join(safecsv.rows(doc.main.columns, doc.main.rows)).encode("utf-8")
            pages = None
        else:
            spec = charts.chart_for(doc, zone)
            view = summary.pdf_view(
                doc, subtitle=summary.TYPES[kind].description,
                filters=filters_text(params, len(stations), zone, kind, p,
                                     now.astimezone(ZoneInfo(zone)).date()),
                zone=zone, generated_at=now, generated_by=job.get("requested_by_name") or "",
                chart=spec.to_view() if spec else None)
            rendered = await svc.renderer.summary(view, TEMPLATE_VERSION)
            body, pages = rendered.pdf, rendered.pages
        key = object_key(job_id, fmt)
        await svc.storage.put(svc.settings.bucket_reports, key, body, CONTENT_TYPES[fmt])
    except data_repo.TooLarge:
        await jobs.fail(svc.db, job_id, "too_large", svc.clock.now())
        return
    except NotFound:
        await jobs.fail(svc.db, job_id, "station_not_found", svc.clock.now())
        return
    except StorageError as e:
        if job["attempts"] >= svc.settings.job_max_attempts:
            log.error("summary_failed", job_id=job_id, reason=type(e).__name__)
            await jobs.fail(svc.db, job_id, "unavailable", svc.clock.now())
            return
        await jobs.requeue(svc.db, job_id, svc.clock.now())
        raise Retry from e
    except Exception:
        log.exception("summary_render_failed", job_id=job_id)
        await jobs.fail(svc.db, job_id, "render_failed", svc.clock.now())
        return
    await jobs.finish(svc.db, job_id, {
        "key": key, "format": fmt, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
        "rows": len(doc.main.rows), "pages": pages, "template_version": TEMPLATE_VERSION,
        "file_name": summary.file_name(kind, p, fmt),
    }, svc.clock.now())


async def purge_old(svc: Services) -> int:
    """Remove summaries past their keep time: the file, then the record. A file that cannot be
    removed leaves its record, so the next run tries again."""
    before = svc.clock.now() - timedelta(days=svc.settings.summary_keep_days)
    removed = 0
    for job in await jobs.older_than(svc.db, JobType.SUMMARY.value, before):
        result = job.get("result")
        try:
            if isinstance(result, dict) and result.get("key"):
                await svc.storage.delete(svc.settings.bucket_reports, result["key"])
        except StorageError:
            log.warning("summary_purge_failed", job_id=job["_id"])
            continue
        await jobs.delete(svc.db, job["_id"])
        removed += 1
    return removed

