"""Prometheus metrics every service shares (TRD §16.5, W20-1).

All metrics are defined here so names and labels stay in one place. **Labels are never
identifiers**: a route is its template (`/api/v1/requests/{id}`), never the path asked for, and
no label holds a user, organization, station, request, token or address.

Services run two uvicorn workers, and `/metrics` is answered by either one, so the API images
set `PROMETHEUS_MULTIPROC_DIR` and `render()` merges the workers' files. Gauges therefore say how
workers combine (`max`, `livesum`, `livemostrecent`). The queue workers are single processes and
serve their own metrics with `serve()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

WORKER_METRICS_PORT = 9100
SKIPPED_PATHS = frozenset({"/metrics", "/health", "/ready"})
UNMATCHED = "unmatched"  # scanners ask for thousands of paths: one label for all of them

LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
JOB_BUCKETS = (0.1, 0.5, 1, 2.5, 5, 15, 30, 60, 120, 300, 600)

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests by route template and status class",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration by route template",
    ["method", "route"], buckets=LATENCY_BUCKETS,
)

OUTBOX_OLDEST = Gauge(
    "outbox_oldest_unpublished_seconds", "Age of the oldest outbox row not yet published",
    multiprocess_mode="max",
)
OUTBOX_LEADER = Gauge(
    "outbox_leader", "1 while this service holds the outbox leader lease", ["topic"],
    multiprocess_mode="max",
)
OUTBOX_LEADER_CHANGES = Counter(
    "outbox_leader_changes_total", "Times a worker became the outbox leader", ["topic"],
)

EVENTS_CONSUMED = Counter(
    "events_consumed_total", "Events handled by a consumer group, by outcome", ["group", "outcome"],
)
DLQ_MESSAGES = Counter("dlq_messages_total", "Messages sent to a dead-letter topic", ["group"])
CONSUMER_BACKLOG = Gauge(
    "consumer_backlog_messages", "Messages waiting for a consumer group", ["group"],
    multiprocess_mode="livesum",
)
CONSUMER_LAG = Gauge(
    "consumer_lag_seconds",
    "Seconds a consumer group has had messages waiting without making progress", ["group"],
    multiprocess_mode="livemax",
)

JOB_DURATION = Histogram(
    "job_duration_seconds", "Queue job duration", ["queue"], buckets=JOB_BUCKETS,
)
JOB_FAILURES = Counter("job_failures_total", "Queue jobs that raised", ["queue"])
JOB_QUEUE_DEPTH = Gauge(
    "job_queue_depth", "Jobs in a Redis queue, claimed ones included", ["queue"],
    multiprocess_mode="livemax",
)
CRON_RUNS = Counter("cron_runs_total", "Scheduled job runs", ["job", "result"])
CRON_LAST_SUCCESS = Gauge(
    "cron_last_success_timestamp_seconds", "Unix time of a scheduled job's last good run",
    ["job"], multiprocess_mode="max",
)

SYNC_OPS = Counter(
    "sync_ops_total", "Offline operations answered by /sync", ["result", "reason"],
)
REPORT_RENDER = Histogram(
    "report_render_seconds", "Time to draw a PDF", ["kind"], buckets=JOB_BUCKETS,
)
REPORTS_FINALIZING_OLDEST = Gauge(
    "reports_finalizing_oldest_seconds", "Age of the report that has been finalizing longest",
    multiprocess_mode="max",
)
CLAMAV_SIGNATURE_AGE = Gauge(
    "clamav_signature_age_seconds", "Age of ClamAV's virus signatures", multiprocess_mode="max",
)


def status_class(code: int) -> str:
    return f"{code // 100}xx"


class MetricsMiddleware:
    """Counts and times each request under its route template. A pure ASGI middleware: the
    router fills `scope["route"]` while the app runs, so it is read after the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in SKIPPED_PATHS:
            await self.app(scope, receive, send)
            return
        status = 500  # an exception that escapes is a 500
        started = time.perf_counter()

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = getattr(scope.get("route"), "path", None) or UNMATCHED
            method = scope["method"] if route != UNMATCHED else "other"
            HTTP_REQUESTS.labels(method, route, status_class(status)).inc()
            HTTP_DURATION.labels(method, route).observe(time.perf_counter() - started)


@contextmanager
def timed(histogram: Histogram, *labels: str) -> Iterator[None]:
    """Observe the seconds a block takes, whether it returns or raises."""
    started = time.perf_counter()
    try:
        yield
    finally:
        histogram.labels(*labels).observe(time.perf_counter() - started)


def age_seconds(then: datetime | None, now: datetime) -> float:
    """Seconds from `then` to `now`; 0 when there is no `then`. Mongo may hand back a naive UTC
    time."""
    if then is None:
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0.0, (now - then).total_seconds())


class LagTracker:
    """Turns "messages are waiting" into "for how long without progress" (consumer_lag_seconds).

    The clock starts when the backlog appears and restarts whenever the group commits, so an idle
    group that suddenly gets a message is not reported as late. `now` is any steadily rising
    number of seconds."""

    def __init__(self) -> None:
        self._since: float | None = None

    def progress(self, now: float) -> None:
        if self._since is not None:
            self._since = now

    def observe(self, backlog: int, now: float) -> float:
        if backlog <= 0:
            self._since = None
            return 0.0
        if self._since is None:
            self._since = now
        return now - self._since


def render() -> tuple[bytes, str]:
    """The `/metrics` body: the merged files of every worker when multiprocess mode is on."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def serve(port: int = WORKER_METRICS_PORT) -> None:
    """For a queue worker, which has no web server: answer `/metrics` on its own port."""
    start_http_server(port)


async def refresh_every(
    seconds: float, update: Callable[[], Awaitable[None]], stop: asyncio.Event
) -> None:
    """Call `update` now and then until `stop`; a failure is logged by the caller's `update`
    and never stops the loop. For gauges that need a query (oldest finalizing report, ClamAV)."""
    while not stop.is_set():
        with contextlib.suppress(Exception):  # a failed reading is retried at the next interval
            await update()
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

