"""platform service entry point (TRD §3.5): the notification and audit modules.

W3 runs the audit module: the consumer that builds the hash chain from every topic. Account
emails (notification) follow in W4; WebSocket and in-app notifications in Phase 3.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mms_common import logging as mms_logging
from mms_common import migrations, mongo
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.jwks import JwksKeys
from mms_common.auth.tokens import KeySource
from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.kafka import consume_forever
from mms_common.time import Clock, SystemClock
from mms_common.web import ReadyCheck, install
from redis.asyncio import Redis

from app import migrations as app_migrations
from app.config import Settings
from app.events import audit_consumer
from app.migrations import audit as audit_migrations


def create_app(
    settings: Settings | None = None,
    ready_checks: dict[str, ReadyCheck] | None = None,
    *,
    clock: Clock | None = None,
    keys: KeySource | None = None,
) -> FastAPI:
    """App factory. Tests pass their own settings, readiness checks, clock and token keys."""
    settings = settings or Settings()
    clock = clock or SystemClock()
    mms_logging.configure(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = mongo.connect(settings.mongo_uri)
        audit_client = mongo.connect(settings.audit_mongo_uri)
        redis = Redis.from_url(settings.redis_url)
        db = client[settings.mongo_db]
        audit_db = audit_client[settings.audit_db]
        app.state.mongo, app.state.db, app.state.redis = client, db, redis
        app.state.audit_mongo, app.state.audit_db = audit_client, audit_db
        install_auth(
            app, Authenticator(keys or JwksKeys(settings.auth_jwks_url, redis, clock), clock, redis)
        )
        if ready_checks is None:

            async def mongo_ok() -> bool:
                await client.admin.command("ping")
                await audit_client.admin.command("ping")
                return True

            async def redis_ok() -> bool:
                return bool(await redis.ping())

            app.state.ready_checks.update({"mongo": mongo_ok, "redis": redis_ok})
        await migrations.run(db, app_migrations, clock)
        await migrations.run(audit_db, audit_migrations, clock)

        stop = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []
        if settings.run_background:

            def make_audit(send_to_dlq: SendToDlq) -> EventProcessor:
                return audit_consumer.processor(audit_client, audit_db, send_to_dlq, clock)

            tasks.append(
                asyncio.create_task(
                    consume_forever(
                        settings.kafka_bootstrap, audit_consumer.GROUP, settings.audit_topics,
                        make_audit, stop,
                    )
                )
            )
        try:
            yield
        finally:
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await redis.aclose()
            await audit_client.close()
            await client.close()

    app = FastAPI(
        title="AWS-MMS platform",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.clock = clock
    install(app, ready_checks)
    # Routers come with their phases: audit search, export and verify (AUD-4 to AUD-6) and
    # notifications. Every route goes in tests/api/test_authorization_matrix.py.
    return app


app = create_app()
