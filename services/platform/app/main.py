"""platform service entry point (TRD §3.5): the notification and audit modules.

The audit module builds the hash chain from every topic (W3). The notification module sends
account emails (W4, NOT-3); WebSocket and in-app notifications follow in Phase 3.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from mms_common import logging as mms_logging
from mms_common import migrations, mongo
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.jwks import JwksKeys
from mms_common.auth.service_client import ServiceTokens
from mms_common.auth.tokens import KeySource
from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.kafka import consume_forever
from mms_common.time import Clock, SystemClock
from mms_common.web import ReadyCheck, install
from redis.asyncio import Redis

from app import migrations as app_migrations
from app.api import notifications as notification_routes
from app.api import ws
from app.config import Settings
from app.events import audit_consumer, notification_consumer
from app.jobs import account_emails, user_backfill
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
        http = httpx.AsyncClient()
        if settings.run_background:

            def make_audit(send_to_dlq: SendToDlq) -> EventProcessor:
                return audit_consumer.processor(audit_client, audit_db, send_to_dlq, clock)

            def make_notification(send_to_dlq: SendToDlq) -> EventProcessor:
                return notification_consumer.processor(client, db, send_to_dlq, clock, redis)

            tokens = ServiceTokens(
                settings.auth_url, "platform", settings.service_secret.get_secret_value(),
                clock, http,
            )
            password = settings.smtp_password
            sender = account_emails.Sender(
                db=db,
                mailer=account_emails.SmtpMailer(
                    settings.smtp_host, settings.smtp_port, settings.smtp_security,
                    settings.smtp_username, password.get_secret_value() if password else None,
                ),
                links=account_emails.AuthLinks(settings.auth_url, tokens, http),
                clock=clock,
                mail_from=settings.mail_from,
                app_url=settings.app_url,
            )
            tasks += [
                asyncio.create_task(
                    consume_forever(
                        settings.kafka_bootstrap, audit_consumer.GROUP, settings.audit_topics,
                        make_audit, stop, settings.kafka,
                    )
                ),
                asyncio.create_task(
                    consume_forever(
                        settings.kafka_bootstrap, notification_consumer.GROUP,
                        settings.notification_topics, make_notification, stop, settings.kafka,
                    )
                ),
                asyncio.create_task(account_emails.run(sender, stop, settings.email_poll_s)),
                asyncio.create_task(
                    user_backfill.run(db, http, tokens, settings.auth_url, stop)
                ),
            ]
        try:
            yield
        finally:
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await http.aclose()
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
    app.include_router(notification_routes.router)
    app.include_router(ws.router)
    # Routers come with their phases: audit search, export and verify (AUD-4 to AUD-6) and
    # the email preferences. Every route goes in tests/api/test_authorization_matrix.py.
    return app


app = create_app()
