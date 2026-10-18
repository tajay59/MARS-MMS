"""Scheduled jobs (TRD §3.3): `abort_stale_uploads` and `reconcile`. Each runs once per
interval across all instances, under a Redis lock (`mms_common.cron`).

`purge_originals` joins them in Phase 4, when images and video have originals to purge.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from mms_common.events import Actor

from app.domain.media import Status
from app.jobs.uploads import enqueue_processing, fail_upload
from app.repo import media as repo
from app.repo.storage import StorageError
from app.services import Services

log = logging.getLogger(__name__)

SYSTEM = Actor(roles=["service"], name="media-cron")
# A worker that died mid-file leaves it in `processing`; a scan of 50 MB takes seconds.
PROCESSING_STALE = timedelta(minutes=30)


async def abort_stale_uploads(svc: Services) -> int:
    """Uploads still open after `stale_upload_hours` (a phone that never came back): abort the
    multipart upload so the store frees its parts, and mark the record failed."""
    cutoff = svc.clock.now() - timedelta(hours=svc.settings.stale_upload_hours)
    count = 0
    for doc in await repo.stuck(svc.db, Status.PENDING, cutoff):
        if doc.get("upload_id"):
            try:
                await svc.storage.abort(svc.bucket(doc["kind"]), doc["original_key"],
                                        doc["upload_id"])
            except StorageError:
                log.exception("abort_failed", extra={"media_id": doc["_id"]})
                continue
        if await fail_upload(svc, doc, "stale", SYSTEM) is not None:
            count += 1
    return count


async def reconcile(svc: Services) -> int:
    """Queue again any file stuck in `uploaded` (the enqueue was lost) and put back any file
    stuck in `processing` (its worker died). Returns how many were queued."""
    now = svc.clock.now()
    queued = 0
    for doc in await repo.stuck(
        svc.db, Status.UPLOADED, now - timedelta(minutes=svc.settings.reconcile_after_minutes)
    ):
        await enqueue_processing(svc, doc["_id"])
        queued += 1
    for doc in await repo.stuck(svc.db, Status.PROCESSING, now - PROCESSING_STALE):
        moved = await repo.transition(svc.db, doc["_id"], Status.PROCESSING, Status.UPLOADED, now)
        if moved is not None:
            await enqueue_processing(svc, doc["_id"])
            queued += 1
    return queued
