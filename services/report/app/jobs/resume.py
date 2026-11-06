"""Taking up what a worker left half done (TRD 11.2; W17-7): `tick` runs every minute under a Redis
lock (`mms_common.cron`).

1. A report left `finalizing` for `finalizing_timeout_s` (the job died, or its retries were lost)
   is queued again. The saga is safe to repeat: the lock is idempotent, the PDF has a key of its
   own and the report becomes final once.
2. An unlock owed to operations (`unlock_pending`: after a stopped finalize or a reopen) is done.
"""

from __future__ import annotations

from datetime import timedelta

from mms_common import metrics

from app.jobs.finalize import job_id, release_lock
from app.repo import reports
from app.services import Services


async def gauge_finalizing(svc: Services) -> None:
    """TRD §16.5: a report in `finalizing` for over 30 minutes raises an alert."""
    since = await reports.oldest_finalizing(svc.db)
    metrics.REPORTS_FINALIZING_OLDEST.set(metrics.age_seconds(since, svc.clock.now()))


async def tick(svc: Services) -> dict[str, int]:
    done = {"resumed": 0, "unlocked": 0}
    before = svc.clock.now() - timedelta(seconds=svc.settings.finalizing_timeout_s)
    for report in await reports.stuck_finalizing(svc.db, before):
        await svc.jobs.enqueue(job_id(report["_id"]))
        done["resumed"] += 1
    for report in await reports.unlock_owed(svc.db):
        await release_lock(svc, report)
        done["unlocked"] += 1
    return done
