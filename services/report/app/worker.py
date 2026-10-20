"""The report-worker: takes jobs from the Redis queue and draws their PDFs (TRD §3.4, §9).

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
from app.jobs.labels import Retry, render_labels
from app.services import QUEUE, Services, make_renderer, make_stations, make_storage

RETRY_DEFER_S = 30
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
    svc = Services(
        settings=settings, clock=clock, client=client, db=client[settings.mongo_db],
        storage=make_storage(settings), stations=make_stations(settings, clock, http),
        renderer=make_renderer(), jobs=NoJobs(),
    )

    async def handle(job_id: str) -> None:
        try:
            await render_labels(svc, job_id)
        except Retry as e:
            raise DeferJob(RETRY_DEFER_S) from e

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
