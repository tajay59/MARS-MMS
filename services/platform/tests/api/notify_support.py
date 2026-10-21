"""Shared parts of the notification tests: events, people, a fake Redis, and the helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest_asyncio
from mms_common.consumer import Outcome
from mms_common.events import Actor, Envelope, Resource
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A as ORG
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock

from app.config import Settings
from app.events.notification_consumer import processor
from app.main import create_app

REQ = "01900000-0000-7000-8000-0000000b0001"
BASE = "https://mms.test"


class FakeRedis:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.down = False

    async def publish(self, channel: str, payload: str) -> int:
        if self.down:
            raise ConnectionError("redis down")
        self.sent.append((channel, json.loads(payload)))
        return 1


def person(key: str, **extra: Any) -> dict[str, Any]:
    u = SEED_USERS[key]
    return {"user_id": u.id, "email": u.email, "name": u.name, "roles": list(u.roles),
            "status": u.status, "org_id": u.org_id, **extra}


def event(type_: str, data: dict[str, Any], *, actor: str | None = None, org: str | None = None,
          key: str = REQ, version: int = 1, source: str = "operations") -> bytes:
    seed = SEED_USERS[actor] if actor else None
    return Envelope(
        event_id=new_id(), type=type_, occurred_at=datetime(2026, 10, 21, 9, tzinfo=UTC),
        source=source, key=key, aggregate_version=version,
        actor=Actor(user_id=seed.id if seed else None, name=seed.name if seed else None,
                    roles=list(seed.roles) if seed else []),
        org_id=org, resource=Resource(type="request", id=key), correlation_id="r",
        data=data,
    ).model_dump_json().encode()


def request_data(**extra: Any) -> dict[str, Any]:
    return {"request_id": REQ, "ref": "MR-2026-0034", "org_id": ORG, "station_ids": [],
            "category": "fault", "priority": "high", "status": "approved",
            "title": "Logger not reporting", "created_by": SEED_USERS["client_a1"].id,
            "assigned_staff_ids": [], **extra}


@pytest_asyncio.fixture
async def env(mongo_uri, redis_url):
    clock = ManualClock(datetime(2026, 10, 21, 9, tzinfo=UTC))
    issuer = TestIssuer(clock)
    suffix = uuid.uuid4().hex[:8]
    settings = Settings(
        mongo_uri=mongo_uri, mongo_db=f"notification_{suffix}", audit_mongo_uri=mongo_uri,
        audit_db=f"audit_{suffix}", redis_url=redis_url, run_background=False,
        ws_heartbeat_s=0.2,
    )
    app = create_app(settings, ready_checks={}, clock=clock, keys=issuer.keys)
    async with app.router.lifespan_context(app):
        dead: list[tuple[bytes, str]] = []

        async def to_dlq(raw: bytes, reason: str) -> None:
            dead.append((raw, reason))

        fake = FakeRedis()
        proc = processor(app.state.mongo, app.state.db, to_dlq, clock, fake)  # type: ignore[arg-type]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
            yield app, http, proc, fake, issuer, clock, dead
        await app.state.mongo.drop_database(settings.mongo_db)
        await app.state.audit_mongo.drop_database(settings.audit_db)


async def directory(proc, *keys: str) -> None:
    """Put people in the directory the way auth's events do."""
    for key in keys:
        raw = event("user.created", {**person(key), "via": "test"}, source="auth",
                    key=SEED_USERS[key].id)
        assert await proc.process(raw) is Outcome.APPLIED


def bearer(issuer: TestIssuer, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {issuer.token(key)}"}


async def listing(http, issuer, key: str, query: str = "") -> dict[str, Any]:
    r = await http.get(f"/api/v1/notifications{query}", headers=bearer(issuer, key))
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


ALL = ("admin", "tech1", "tech2", "viewer", "client_a1", "client_a2")
