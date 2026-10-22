"""operations service entry point (TRD §3.2).

Phase 2 builds the stations module: stations, sensor models and units, installations,
calibrations and the station import. Phase 3 adds the requests module (W8: create, read,
edit, approve, deny, cancel); visits (Phase 4) join it.
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
from mms_common.auth.service_client import ServiceTokens
from mms_common.auth.tokens import KeySource
from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.ids import new_id
from mms_common.kafka import consume_forever, producer_factory
from mms_common.outbox import LeaderLease
from mms_common.relay import run_relay
from mms_common.time import Clock, SystemClock
from mms_common.web import ReadyCheck, install
from redis.asyncio import Redis

from app import migrations as app_migrations
from app.api import internal_routes
from app.api.checklists import template_routes
from app.api.requests import comment_routes, queue_routes, request_routes
from app.api.stations import (
    calibration_routes,
    config_routes,
    document_routes,
    qr_routes,
    sensor_routes,
    station_routes,
)
from app.api.visits import visit_routes, work_routes
from app.config import Settings
from app.events import consumer
from app.jobs import org_backfill
from app.repo.requests.staff_client import StaffApi, StaffClient
from app.repo.stations.media_client import MediaApi, MediaClient


def create_app(
    settings: Settings | None = None,
    ready_checks: dict[str, ReadyCheck] | None = None,
    *,
    clock: Clock | None = None,
    keys: KeySource | None = None,
    media: MediaApi | None = None,
    staff: StaffApi | None = None,
) -> FastAPI:
    """App factory. Tests pass their own settings, readiness checks, clock and token keys."""
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

        stop = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []
        http = httpx.AsyncClient()
        tokens = ServiceTokens(
            settings.auth_url, "operations", settings.service_secret.get_secret_value(),
            clock, http,
        )
        app.state.media = media or MediaClient(settings.media_url, tokens, http)
        app.state.staff = staff or StaffClient(settings.auth_url, tokens, http)
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
                asyncio.create_task(org_backfill.run(db, http, tokens, settings.auth_url, stop)),
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
        title="AWS-MMS operations",
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
        """API responses never sit in a browser, proxy or service-worker cache (§13.3)."""
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Literal paths before /{id} (TRD §3.0): each router declares its own in that order.
    # Every route goes in tests/api/test_authorization_matrix.py.
    app.include_router(station_routes.router)
    app.include_router(qr_routes.station_router)
    app.include_router(qr_routes.router)
    app.include_router(sensor_routes.model_router)
    app.include_router(sensor_routes.unit_router)
    app.include_router(calibration_routes.router)
    app.include_router(document_routes.router)
    app.include_router(document_routes.station_router)
    app.include_router(config_routes.router)
    app.include_router(request_routes.router)
    app.include_router(queue_routes.router)
    app.include_router(comment_routes.router)
    app.include_router(visit_routes.router)
    app.include_router(work_routes.router)
    app.include_router(template_routes.router)
    app.include_router(internal_routes.router)
    return app


app = create_app()
