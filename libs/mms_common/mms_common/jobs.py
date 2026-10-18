"""A small job queue on Redis, for work that should not run inside a request (TRD §9).

One sorted set per queue holds job IDs scored by the time they are due. A worker *claims* a
due job by pushing its score `visibility_s` into the future, and *acks* it by removing it. If
the worker dies, the job becomes due again by itself, so every job runs at least once. Jobs
must therefore be safe to repeat: the media worker moves a file between states with
conditional updates, so a second run finds nothing to do.

`enqueue` is idempotent: a job ID already in the queue keeps its place (so a file queued twice
runs once, and a job being worked on is not queued again).

(arq was the plan, but it pins `redis<6`, which the rest of the stack has moved past.)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis

from mms_common.logging import get_logger

log = get_logger(__name__)

# Claim the earliest due job: move its score to the lease end and return it. Atomic.
_CLAIM = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)
if #due == 0 then return false end
redis.call('ZADD', KEYS[1], ARGV[2], due[1])
return due[1]
"""


class Retry(Exception):  # noqa: N818 - reads as the instruction it is
    """Raised by a handler to run the job again after `defer_s` seconds."""

    def __init__(self, defer_s: float = 60.0) -> None:
        super().__init__(f"retry in {defer_s}s")
        self.defer_s = defer_s


class JobQueue:
    def __init__(self, store: Redis, name: str, visibility_s: float = 600.0) -> None:
        self._store = store
        self.name = f"jobs:{name}"
        self._visibility_s = visibility_s

    async def enqueue(self, job_id: str, *, defer_s: float = 0.0) -> bool:
        """Queue a job, unless this ID is already queued. True when it was added."""
        added = await self._store.zadd(self.name, {job_id: time.time() + defer_s}, nx=True)
        return bool(added)

    async def claim(self) -> str | None:
        now = time.time()
        job: Any = await self._store.eval(_CLAIM, 1, self.name, now, now + self._visibility_s)
        if not job:
            return None
        return job.decode() if isinstance(job, bytes) else str(job)

    async def ack(self, job_id: str) -> None:
        await self._store.zrem(self.name, job_id)

    async def reschedule(self, job_id: str, defer_s: float) -> None:
        """Run the job again after `defer_s` (it is currently claimed)."""
        await self._store.zadd(self.name, {job_id: time.time() + defer_s}, xx=True)

    async def size(self) -> int:
        return int(await self._store.zcard(self.name))


async def run_worker(
    queue: JobQueue,
    handler: Callable[[str], Awaitable[Any]],
    stop: asyncio.Event,
    *,
    concurrency: int = 4,
    poll_s: float = 1.0,
) -> None:
    """Take due jobs and run `handler(job_id)` until `stop` is set. A handler that returns
    acks the job; `Retry` puts it back for later; any other error is logged and the job comes
    back when its lease runs out."""
    running: set[asyncio.Task[None]] = set()

    async def run(job_id: str) -> None:
        try:
            await handler(job_id)
        except Retry as r:
            await queue.reschedule(job_id, r.defer_s)
        except Exception:  # noqa: BLE001 - leave the lease to expire; the job runs again
            log.exception("job_failed", queue=queue.name, job_id=job_id)
        else:
            await queue.ack(job_id)

    while not stop.is_set():
        if len(running) < concurrency:
            job_id = await queue.claim()
            if job_id is not None:
                task = asyncio.create_task(run(job_id))
                running.add(task)
                task.add_done_callback(running.discard)
                continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_s)
        except TimeoutError:
            pass
    if running:
        await asyncio.gather(*running, return_exceptions=True)
