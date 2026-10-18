"""The Redis job queue (TRD §9): a job runs at least once, is queued once, and comes back when
its worker dies. Against a real Redis."""

from __future__ import annotations

import asyncio
import uuid

import pytest_asyncio
from redis.asyncio import Redis

from mms_common.jobs import JobQueue, Retry, run_worker


@pytest_asyncio.fixture
async def redis(redis_url):
    client = Redis.from_url(redis_url)
    yield client
    await client.aclose()


def queue(redis, **kw) -> JobQueue:
    return JobQueue(redis, f"t-{uuid.uuid4().hex[:6]}", **kw)


async def test_enqueue_is_idempotent_and_claim_takes_one_job_at_a_time(redis):
    q = queue(redis)
    assert await q.enqueue("a")
    assert not await q.enqueue("a")  # already queued: keeps its place
    assert await q.enqueue("b")
    first = await q.claim()
    second = await q.claim()
    assert {first, second} == {"a", "b"}
    assert await q.claim() is None  # both are leased, none is due


async def test_a_claimed_job_is_not_queued_again_until_acked(redis):
    q = queue(redis)
    await q.enqueue("a")
    assert await q.claim() == "a"
    assert not await q.enqueue("a")  # in flight
    await q.ack("a")
    assert await q.size() == 0
    assert await q.enqueue("a")  # finished work can be queued again


async def test_a_job_comes_back_when_its_lease_runs_out(redis):
    q = queue(redis, visibility_s=0.2)
    await q.enqueue("a")
    assert await q.claim() == "a"  # the worker "dies" here
    assert await q.claim() is None
    await asyncio.sleep(0.3)
    assert await q.claim() == "a"


async def test_deferred_jobs_wait(redis):
    q = queue(redis)
    await q.enqueue("later", defer_s=0.3)
    assert await q.claim() is None
    await asyncio.sleep(0.4)
    assert await q.claim() == "later"


async def test_worker_runs_acks_and_retries(redis):
    q = queue(redis, visibility_s=30)
    seen: list[str] = []
    attempts = {"retry-me": 0}

    async def handler(job_id: str) -> None:
        seen.append(job_id)
        if job_id == "retry-me":
            attempts[job_id] += 1
            if attempts[job_id] == 1:
                raise Retry(0.1)

    await q.enqueue("ok")
    await q.enqueue("retry-me")
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(q, handler, stop, poll_s=0.05))
    for _ in range(100):
        if await q.size() == 0:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await task
    assert seen.count("ok") == 1
    assert seen.count("retry-me") == 2
    assert await q.size() == 0


async def test_a_failing_handler_leaves_the_job_to_come_back(redis):
    q = queue(redis, visibility_s=0.2)
    calls = 0

    async def handler(job_id: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")

    await q.enqueue("a")
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(q, handler, stop, poll_s=0.05))
    for _ in range(100):
        if calls >= 2 and await q.size() == 0:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await task
    assert calls == 2
