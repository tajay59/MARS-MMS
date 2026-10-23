"""report service entry point (TRD §3.4).

Phase 2 builds the skeleton: the render pipeline (Jinja templates, WeasyPrint) and the label
sheet (QR-6). Visit reports, close-outs, summaries and the dashboard follow in Phases 6 and 7.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from mms_common import logging as mms_logging
from mms_common import migrations, mongo
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.jwks import JwksKeys
from mms_common.auth.tokens import KeySource
from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.ids import new_id
from mms_common.jobs import JobQueue
from mms_common.kafka import consume_forever, producer_factory
from mms_common.outbox import LeaderLease
from mms_common.relay import run_relay
from mms_common.time import Clock, SystemClock
from mms_common.web import ReadyCheck, install
from redis.asyncio import Redis

from app import migrations as app_migrations
from app.api import reports
from app.config import Settings
from app.events import consumer
from app.jobs import backfill
from app.repo.operations import LabelSource
from app.repo.render import Renderer
from app.repo.storage import Storage
from app.services import (
    QUEUE,
    Jobs,
    QueueJobs,
    Services,
    make_renderer,
    make_stations,
    make_storage,
)


def create_app(
    settings: Settings | None = None,
    ready_checks: dict[str, ReadyCheck] | None = None,
    *,
    clock: Clock | None = None,
    keys: KeySource | None = None,
    storage: Storage | None = None,
    stations: LabelSource | None = None,
    renderer: Renderer | None = None,
    jobs: Jobs | None = None,
) -> FastAPI:
    """App factory. Tests pass their own settings, readiness checks, clock, token keys and
    stand-ins for the store, operations, the PDF renderer and the job queue."""
    settings = settings or Settings()
    clock = clock or SystemClock()
    mms_logging.configure(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = mongo.connect(settings.mongo_uri)
        redis = Redis.from_url(settings.redis_url)
        db = client[settings.mongo_db]
        app.state.mongo, app.state.db, app.state.redis = client, db, redis
        install_auth(
            app, Authenticator(keys or JwksKeys(settings.auth_jwks_url, redis, clock), clock, redis)
        )
        if ready_checks is None:

            async def mongo_ok() -> bool:
                await client.admin.command("ping")
                return True

            async def redis_ok() -> bool:
                return bool(await redis.ping())

            app.state.ready_checks.update({"mongo": mongo_ok, "redis": redis_ok})
        await migrations.run(db, app_migrations, clock)

        http = httpx.AsyncClient()
        operations = make_stations(settings, clock, http)
        app.state.services = Services(
            settings=settings, clock=clock, client=client, db=db,
            storage=storage or make_storage(settings),
            stations=stations or operations,
            renderer=renderer or make_renderer(),
            jobs=jobs or QueueJobs(JobQueue(redis, QUEUE)),
        )

        stop = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []
        # Cron jobs (mms_common.cron.run_periodic) start here too, each with `stop`, when
        # run_background is on.
        if settings.run_background:
            # The outbox relay runs in every worker; only the lease holder publishes (§8.2).
            lease = LeaderLease(redis, settings.service_name, new_id())
            relay = run_relay(
                db["outbox"],
                lease,
                producer_factory(settings.kafka_bootstrap, settings.service_name, settings.kafka),
                settings.outbox_topic,
                clock,
                stop,
            )

            def make_consumer(send_to_dlq: SendToDlq) -> EventProcessor:
                return consumer.processor(client, db, send_to_dlq, clock)

            tasks += [
                asyncio.create_task(relay),
                asyncio.create_task(
                    consume_forever(
                        settings.kafka_bootstrap, consumer.GROUP, consumer.TOPICS,
                        make_consumer, stop, settings.kafka,
                    )
                ),
                # The read model covers everything entered since Phase 2, and the consumer group
                # starts at the oldest event Kafka still holds (TRD §8.6)
                asyncio.create_task(backfill.run(db, operations, stop)),
            ]
        try:
            yield
        finally:
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await http.aclose()
            await redis.aclose()
            await client.close()

    app = FastAPI(
        title="AWS-MMS report",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.clock = clock
    install(app, ready_checks)

    @app.middleware("http")
    async def no_store(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """API responses never sit in a browser, proxy or service-worker cache (§13.3). The
        download link in a job's answer acts as a password for ten minutes."""
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Literal paths before /{id} (TRD §3.0). Every route goes in the authorization matrix.
    app.include_router(reports.router)
    return app


app = create_app()
