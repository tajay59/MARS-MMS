"""media service entry point (TRD §3.3).

Phase 2 builds the documents path: presigned multipart uploads, the owner check, fail-closed
visibility, the virus scan and the two cron jobs. Images and video follow in Phase 4.
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
from mms_common.cron import run_periodic
from mms_common.ids import new_id
from mms_common.jobs import JobQueue
from mms_common.kafka import consume_forever, producer_factory
from mms_common.outbox import LeaderLease
from mms_common.relay import run_relay
from mms_common.time import Clock, SystemClock
from mms_common.web import ReadyCheck, install
from redis.asyncio import Redis

from app import migrations as app_migrations
from app.api import internal, media, uploads
from app.config import Settings
from app.events import visibility_consumer
from app.jobs import cron
from app.repo.owners import OwnerClient
from app.repo.scanner import Scanner
from app.repo.storage import Storage
from app.services import (
    QUEUE,
    Jobs,
    QueueJobs,
    Services,
    make_owners,
    make_scanner,
    make_storage,
)

ABORT_STALE_EVERY_S = 24 * 3600
PURGE_EVERY_S = 24 * 3600
RECONCILE_EVERY_S = 5 * 60


def create_app(
    settings: Settings | None = None,
    ready_checks: dict[str, ReadyCheck] | None = None,
    *,
    clock: Clock | None = None,
    keys: KeySource | None = None,
    storage: Storage | None = None,
    scanner: Scanner | None = None,
    owners: OwnerClient | None = None,
    jobs: Jobs | None = None,
) -> FastAPI:
    """App factory. Tests pass their own settings, readiness checks, clock, token keys and
    stand-ins for the store, scanner, owner check and job queue."""
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
        queue = jobs or QueueJobs(JobQueue(redis, QUEUE))
        svc = Services(
            settings=settings, clock=clock, client=client, db=db,
            storage=storage or make_storage(settings),
            scanner=scanner or make_scanner(settings),
            owners=owners or make_owners(settings, clock, http),
            jobs=queue,
        )
        app.state.services = svc

        stop = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []
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

            def make_visibility(send_to_dlq: SendToDlq) -> EventProcessor:
                return visibility_consumer.processor(client, db, send_to_dlq, clock)

            async def abort_stale() -> None:
                await cron.abort_stale_uploads(svc)

            async def reconcile() -> None:
                await cron.reconcile(svc)

            async def purge() -> None:
                await cron.purge_originals(svc)
                await cron.purge_deleted(svc)

            tasks += [
                asyncio.create_task(relay),
                asyncio.create_task(
                    consume_forever(
                        settings.kafka_bootstrap, visibility_consumer.GROUP,
                        visibility_consumer.TOPICS, make_visibility, stop, settings.kafka,
                    )
                ),
                asyncio.create_task(run_periodic(
                    redis, settings.service_name, "abort_stale_uploads", ABORT_STALE_EVERY_S,
                    abort_stale, stop,
                )),
                asyncio.create_task(run_periodic(
                    redis, settings.service_name, "reconcile", RECONCILE_EVERY_S, reconcile, stop,
                )),
                asyncio.create_task(run_periodic(
                    redis, settings.service_name, "purge_originals", PURGE_EVERY_S, purge, stop,
                )),
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
        title="AWS-MMS media",
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
        upload and download links in them act as passwords for a while."""
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Literal paths before /{id} (TRD §3.0). Every route goes in the authorization matrix.
    app.include_router(uploads.router)
    app.include_router(media.router)
    app.include_router(internal.router)
    return app


app = create_app()
