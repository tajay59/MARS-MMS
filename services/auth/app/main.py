"""auth service entry point (TRD §3.1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from mms_common import logging as mms_logging
from mms_common import migrations, mongo
from mms_common.auth import Authenticator, install_auth
from mms_common.auth.tokens import SigningKey, StaticKeys
from mms_common.cron import run_periodic
from mms_common.ids import new_id
from mms_common.kafka import producer_factory
from mms_common.outbox import LeaderLease
from mms_common.relay import run_relay
from mms_common.time import Clock, SystemClock
from mms_common.web import PROBLEM, ReadyCheck, install
from redis.asyncio import Redis

from app import migrations as app_migrations
from app.api import admin_routes, internal_routes, session_routes
from app.api.context import COOKIE_PATH
from app.config import Settings
from app.domain.passwords import BreachedCheck, Hasher
from app.jobs.purge import purge_pending
from app.repo import keys
from app.repo.breached import FileCheck, HibpCheck, NoCheck

PURGE_EVERY_S = 24 * 3600


def breached_check(settings: Settings) -> BreachedCheck:
    local = FileCheck(settings.breached_file) if settings.breached_file else None
    if settings.breached_check == "off":
        return NoCheck()
    if settings.breached_check == "file":
        if local is None:
            raise ValueError("AUTH_BREACHED_CHECK=file needs AUTH_BREACHED_FILE")
        return local
    return HibpCheck(settings.hibp_url, settings.hibp_timeout_s, fallback=local)


def create_app(
    settings: Settings | None = None,
    ready_checks: dict[str, ReadyCheck] | None = None,
    *,
    clock: Clock | None = None,
    signing_key: SigningKey | None = None,
    breached: BreachedCheck | None = None,
) -> FastAPI:
    """App factory. Tests pass their own settings, clock, signing key and breached list."""
    settings = settings or Settings()
    clock = clock or SystemClock()
    mms_logging.configure(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = mongo.connect(settings.mongo_uri)
        redis = Redis.from_url(settings.redis_url)
        db = client[settings.mongo_db]
        app.state.mongo, app.state.db, app.state.redis = client, db, redis
        if ready_checks is None:

            async def mongo_ok() -> bool:
                await client.admin.command("ping")
                return True

            async def redis_ok() -> bool:
                return bool(await redis.ping())

            app.state.ready_checks.update({"mongo": mongo_ok, "redis": redis_ok})
        await migrations.run(db, app_migrations, clock)

        signing = signing_key or keys.load(settings.signing_key_file)
        await keys.activate(db, signing, settings.signing_key_file, clock.now())
        app.state.signing = signing
        # auth verifies its own tokens with the keys it publishes, not over HTTP.
        verify_keys = StaticKeys(await keys.published(db, clock.now()))
        install_auth(app, Authenticator(verify_keys, clock, redis))

        stop = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []
        if settings.run_background:
            # The outbox relay runs in every worker; only the lease holder publishes (§8.2).
            lease = LeaderLease(redis, settings.service_name, new_id())
            relay = run_relay(
                db["outbox"],
                lease,
                producer_factory(settings.kafka_bootstrap, settings.service_name),
                settings.outbox_topic,
                clock,
                stop,
            )
            tasks.append(asyncio.create_task(relay))

            async def purge() -> None:
                await purge_pending(client, db, clock, settings.pending_purge_days)

            tasks.append(
                asyncio.create_task(
                    run_periodic(redis, "auth", "purge_pending", PURGE_EVERY_S, purge, stop)
                )
            )
        try:
            yield
        finally:
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await redis.aclose()
            await client.close()

    app = FastAPI(
        title="AWS-MMS auth",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.hasher = Hasher(
        settings.argon2_time_cost, settings.argon2_memory_kib, settings.argon2_parallelism
    )
    app.state.breached = breached or breached_check(settings)
    install(app, ready_checks)

    @app.middleware("http")
    async def no_store(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Tokens and account data must never sit in a browser or proxy cache (§13.3)."""
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(session_routes.SessionEnded)
    async def session_ended(request: Request, exc: session_routes.SessionEnded) -> JSONResponse:
        """A failed refresh also clears the refresh cookie."""
        response = JSONResponse(
            exc.problem(getattr(request.state, "request_id", None)),
            status_code=exc.status,
            media_type=PROBLEM,
        )
        for name in ("__Secure-mms_refresh", "mms_refresh"):
            response.delete_cookie(
                name, path=COOKIE_PATH, secure=settings.cookie_secure, httponly=True,
                samesite="strict",
            )
        return response

    # Literal paths before /{id} (TRD §3.0): each router declares its own in that order.
    app.include_router(session_routes.router)
    app.include_router(admin_routes.users)
    app.include_router(admin_routes.orgs)
    app.include_router(internal_routes.router)
    return app


app = create_app()
