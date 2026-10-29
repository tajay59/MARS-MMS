"""Metrics (TRD §16.5, W20-1): names and labels, no identifiers in labels, the lag clock, the
queue, cron and outbox readings, and the merged /metrics of two workers."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from prometheus_client import REGISTRY
from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from mms_common import metrics, outbox
from mms_common.cron import run_once_locked
from mms_common.events import Envelope, Resource
from mms_common.ids import new_id
from mms_common.jobs import JobQueue, run_worker
from mms_common.mongo import in_transaction
from mms_common.relay import _gauge_oldest
from mms_common.time import ManualClock
from mms_common.web import install


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def make_app() -> FastAPI:
    app = FastAPI()
    install(app)

    @app.get("/w20/n/{n}")
    async def n(n: int):
        return {"n": n}

    @app.get("/w20/boom")
    async def boom():
        raise RuntimeError("bug")

    return app


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    )


async def test_requests_are_counted_under_the_route_template_not_the_path():
    before = sample("http_requests_total", method="GET", route="/w20/n/{n}", status="2xx")
    async with client(make_app()) as c:
        await c.get("/w20/n/1?token=abc")
        await c.get("/w20/n/secret-person-42")  # fails validation: a 4xx under the same route
        await c.get("/w20/n/2")
        text = (await c.get("/metrics")).text
    ok = sample("http_requests_total", method="GET", route="/w20/n/{n}", status="2xx")
    assert ok - before == 2
    assert sample("http_requests_total", method="GET", route="/w20/n/{n}", status="4xx") >= 1
    assert "secret-person-42" not in text and "token" not in text
    assert 'route="/w20/n/1"' not in text


async def test_unknown_paths_share_one_label_and_a_crash_is_a_5xx():
    before = sample("http_requests_total", method="other", route="unmatched", status="4xx")
    five = sample("http_requests_total", method="GET", route="/w20/boom", status="5xx")
    async with client(make_app()) as c:
        for path in ("/wp-login.php", "/.env", "/a/b/c"):
            await c.get(path)
        await c.get("/w20/boom")
    unmatched = sample("http_requests_total", method="other", route="unmatched", status="4xx")
    assert unmatched - before == 3
    assert sample("http_requests_total", method="GET", route="/w20/boom", status="5xx") - five == 1


async def test_health_ready_and_metrics_are_not_counted():
    async with client(make_app()) as c:
        for path in ("/health", "/ready"):
            await c.get(path)
        text = (await c.get("/metrics")).text
    for path in ("/health", "/ready", "/metrics"):
        assert f'route="{path}"' not in text


def test_the_lag_clock_starts_when_work_appears_and_restarts_on_progress():
    t = metrics.LagTracker()
    assert t.observe(0, 0) == 0
    assert t.observe(3, 100) == 0  # a message just arrived at an idle group: not late
    assert t.observe(3, 130) == 30
    t.progress(140)
    assert t.observe(2, 150) == 10
    assert t.observe(0, 160) == 0
    assert t.observe(1, 300) == 0  # idle for a long time, then one message


def test_age_handles_naive_times_and_missing_rows():
    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    assert metrics.age_seconds(None, now) == 0
    assert metrics.age_seconds(datetime(2026, 10, 29, 11, 55), now) == 300  # naive = UTC
    assert metrics.age_seconds(datetime(2026, 10, 29, 12, 5, tzinfo=UTC), now) == 0


@pytest_asyncio.fixture
async def redis(redis_url):
    r = Redis.from_url(redis_url)
    yield r
    await r.aclose()


async def test_a_queue_worker_times_jobs_counts_failures_and_reports_depth(redis):
    name = f"m-{uuid.uuid4().hex[:6]}"
    q = JobQueue(redis, name)
    for job in ("ok", "bad"):
        await q.enqueue(job)

    async def handle(job_id: str) -> None:
        if job_id == "bad":
            raise ValueError("boom")

    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(q, handle, stop, poll_s=0.05))
    for _ in range(100):
        if sample("job_failures_total", queue=q.name) >= 1:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await task
    assert sample("job_failures_total", queue=q.name) == 1
    assert sample("job_duration_seconds_count", queue=q.name) == 2
    assert sample("job_queue_depth", queue=q.name) >= 1  # the failed job waits for its lease


async def test_cron_records_the_last_good_run_and_each_failure(redis):
    job = f"c{uuid.uuid4().hex[:6]}"

    async def good() -> None:
        return None

    async def bad() -> None:
        raise RuntimeError("x")

    assert await run_once_locked(redis, "svc", job, 60, good)
    assert sample("cron_runs_total", job=job, result="ok") == 1
    assert sample("cron_last_success_timestamp_seconds", job=job) > 1.7e9
    other = f"c{uuid.uuid4().hex[:6]}"
    assert await run_once_locked(redis, "svc", other, 60, bad)
    assert sample("cron_runs_total", job=other, result="error") == 1
    assert sample("cron_last_success_timestamp_seconds", job=other) == 0


async def test_the_outbox_gauge_is_the_age_of_the_oldest_waiting_row(mongo_uri, mongo):
    clock = ManualClock(datetime(2026, 10, 29, 12, 0, tzinfo=UTC))
    client_: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    col = client_[mongo.name]["outbox"]
    await outbox.ensure_indexes(col)
    await _gauge_oldest(col, clock)
    assert sample("outbox_oldest_unpublished_seconds") == 0  # nothing waiting

    env = Envelope(
        event_id=new_id(), type="user.updated", occurred_at=clock.now(), source="auth", key="u1",
        aggregate_version=1, resource=Resource(type="user", id="u1"),
    )
    await in_transaction(client_, lambda s: outbox.add(col, env, session=s, clock=clock))
    clock.advance(seconds=400)
    await _gauge_oldest(col, clock)
    assert sample("outbox_oldest_unpublished_seconds") == 400

    await col.update_many({}, {"$set": {"published_at": clock.now()}})
    await _gauge_oldest(col, clock)
    assert sample("outbox_oldest_unpublished_seconds") == 0
    await client_.close()


WORKER = """
import sys
from mms_common import metrics
metrics.HTTP_REQUESTS.labels("GET", "/w20/mp", "2xx").inc()
metrics.OUTBOX_OLDEST.set(float(sys.argv[1]))
if len(sys.argv) > 2:
    print(metrics.render()[0].decode())
"""


def test_two_workers_are_merged_into_one_metrics_answer(tmp_path):
    """Both uvicorn workers write files into PROMETHEUS_MULTIPROC_DIR and either answers
    `/metrics` with the sum of counters and the largest `max` gauge."""
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    for value in ("30", "90"):
        subprocess.run([sys.executable, "-c", WORKER, value], env=env, check=True)
    out = subprocess.run(
        [sys.executable, "-c", WORKER, "10", "print"], env=env, check=True, capture_output=True,
        text=True,
    ).stdout
    assert 'http_requests_total{method="GET",route="/w20/mp",status="2xx"} 3.0' in out
    assert "outbox_oldest_unpublished_seconds 90.0" in out


@pytest.mark.parametrize("name", sorted(
    n for n in (
        "http_requests_total", "http_request_duration_seconds", "outbox_oldest_unpublished_seconds",
        "outbox_leader", "outbox_leader_changes_total", "consumer_backlog_messages",
        "consumer_lag_seconds", "events_consumed_total", "dlq_messages_total",
        "job_duration_seconds", "job_failures_total", "sync_ops_total", "report_render_seconds",
        "reports_finalizing_oldest_seconds", "clamav_signature_age_seconds",
    )
))
def test_every_metric_the_alerts_use_exists(name):
    """The names in infra/monitoring/rules are these (TRD §16.5)."""
    exposed = {m.name for m in REGISTRY.collect()}
    assert name.removesuffix("_total") in exposed
