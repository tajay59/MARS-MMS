"""The media-worker: takes files from the Redis queue and runs `process_media` on them
(TRD §3.3, §9).

    python -m app.worker

It shares the image with the API and has no HTTP port. Images and video join in Phase 4.
"""

from __future__ import annotations

import asyncio
import signal

import httpx
from mms_common import logging as mms_logging
from mms_common import mongo
from mms_common.jobs import JobQueue, Retry, run_worker
from mms_common.time import SystemClock
from redis.asyncio import Redis

from app.config import Settings
from app.jobs.process import Retry as ProcessRetry
from app.jobs.process import process_media
from app.services import QUEUE, Services, make_owners, make_scanner, make_storage

RETRY_DEFER_S = 60


class NoJobs:
    """The worker only consumes the queue."""

    async def enqueue(self, media_id: str) -> None:
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
        storage=make_storage(settings), scanner=make_scanner(settings),
        owners=make_owners(settings, clock, http), jobs=NoJobs(),
    )

    async def handle(media_id: str) -> None:
        try:
            await process_media(svc, media_id)
        except ProcessRetry as e:
            # Scanner or store unreachable: back off. The file is back in `uploaded`, and
            # `reconcile` is the safety net if this worker stops.
            raise Retry(RETRY_DEFER_S) from e

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run_worker(JobQueue(redis, QUEUE), handle, stop, concurrency=4)
    finally:
        await http.aclose()
        await redis.aclose()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
