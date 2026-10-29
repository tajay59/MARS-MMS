"""The report-worker: takes jobs from the Redis queue and draws their PDFs (TRD §3.4, §9):
label sheets, visit reports, client form reports and close-outs.

    python -m app.worker

It shares the image with the API and has no HTTP port.
"""

from __future__ import annotations

import asyncio
import signal

import httpx
from mms_common import logging as mms_logging
from mms_common import mongo
from mms_common.jobs import JobQueue, run_worker
from mms_common.jobs import Retry as DeferJob
from mms_common.time import SystemClock
from redis.asyncio import Redis

from app.config import Settings
from app.jobs.finalize import finalize_report
from app.jobs.labels import Retry, render_labels
from app.jobs.render_client_form import render_client_form
from app.jobs.render_closeout import render_closeout
from app.jobs.render_draft import render_draft
from app.jobs.summary import render_summary
from app.services import (
    QUEUE,
    Services,
    make_media,
    make_renderer,
    make_stations,
    make_storage,
)

RETRY_DEFER_S = 30
DRAFT_PREFIX = "draft:"  # a visit report draft's job is `draft:<report id>`
FINALIZE_PREFIX = "finalize:"  # and finalizing one is `finalize:<report id>`
CLIENT_FORM_PREFIX = "clientform:"  # a client form report is `clientform:<report id>`
CLOSEOUT_PREFIX = "closeout:"  # and a request's close-out is `closeout:<report id>`
SUMMARY_PREFIX = "summary:"  # a summary report is `summary:<job id>` (W19)
CONCURRENCY = 2  # TRD §9: two report jobs at a time


class NoJobs:
    """The worker only consumes the queue."""

    async def enqueue(self, job_id: str) -> None:
        raise RuntimeError("the worker does not queue jobs")


async def main() -> None:
    settings = Settings()
    mms_logging.configure(settings.service_name + "-worker", settings.log_level)
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    redis = Redis.from_url(settings.redis_url)
    http = httpx.AsyncClient()
    operations = make_stations(settings, clock, http)
    svc = Services(
        settings=settings, clock=clock, client=client, db=client[settings.mongo_db],
        storage=make_storage(settings), stations=operations, renderer=make_renderer(settings),
        jobs=NoJobs(), facts=operations, media=make_media(settings, clock, http),
        locks=operations,
    )

    async def handle(job_id: str) -> None:
        try:
            if job_id.startswith(DRAFT_PREFIX):
                await render_draft(svc, job_id[len(DRAFT_PREFIX):])
            elif job_id.startswith(FINALIZE_PREFIX):
                await finalize_report(svc, job_id[len(FINALIZE_PREFIX):])
            elif job_id.startswith(CLOSEOUT_PREFIX):
                await render_closeout(svc, job_id[len(CLOSEOUT_PREFIX):])
            elif job_id.startswith(SUMMARY_PREFIX):
                await render_summary(svc, job_id[len(SUMMARY_PREFIX):])
            elif job_id.startswith(CLIENT_FORM_PREFIX):
                await render_client_form(svc, job_id[len(CLIENT_FORM_PREFIX):])
            else:
                await render_labels(svc, job_id)
        except Retry as e:
            raise DeferJob(e.defer_s or RETRY_DEFER_S) from e

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run_worker(JobQueue(redis, QUEUE), handle, stop, concurrency=CONCURRENCY)
    finally:
        await http.aclose()
        await redis.aclose()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
