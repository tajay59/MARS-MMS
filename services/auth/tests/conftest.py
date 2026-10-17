"""auth test fixtures: the real app with its lifespan on throwaway Mongo and Redis, a manual
clock, the seed users (TP), and helpers to read the outbox."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest_asyncio
from argon2 import PasswordHasher
from mms_common.events import Envelope, validate
from mms_common.ids import new_id
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from pymongo import AsyncMongoClient

from app.config import Settings
from app.main import create_app

pytest_plugins = ["mms_common.testing.containers"]

PASSWORD = "correct horse battery"  # noqa: S105 - every seed user's password, tests only
BASE = "https://mms.test"
_HASH = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1).hash(PASSWORD)


class Breached:
    def __init__(self) -> None:
        self.passwords = {"pwned password 1"}

    async def is_breached(self, password: str) -> bool:
        return password in self.passwords


@dataclass
class Auth:
    app: Any
    http: httpx.AsyncClient
    db: Any
    clock: ManualClock
    issuer: TestIssuer
    redis: Any
    breached: Breached
    settings: Settings
    clients: list[httpx.AsyncClient] = field(default_factory=list)

    def client(self) -> httpx.AsyncClient:
        """Another browser (its own cookie jar) against the same app."""
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=BASE)
        self.clients.append(c)
        return c

    def bearer(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issuer.token(who)}"}

    async def outbox(self, type_: str | None = None) -> list[Envelope]:
        """Outbox rows, oldest first, each validated against its schema (contract check)."""
        query = {"type": type_} if type_ else {}
        cursor = self.db["outbox"].find(query).sort([("created_at", 1), ("_id", 1)])
        rows = [r async for r in cursor]
        envelopes = []
        for row in rows:
            env = Envelope.model_validate(
                {k: v for k, v in row.items() if k not in ("_id", "created_at", "published_at")}
            )
            validate(env)
            envelopes.append(env)
        return envelopes

    async def login(
        self, email: str, password: str = PASSWORD, client: httpx.AsyncClient | None = None
    ) -> httpx.Response:
        return await (client or self.http).post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )

    async def user(self, key: str) -> dict[str, Any]:
        doc: dict[str, Any] = await self.db["users"].find_one({"_id": SEED_USERS[key].id})
        return doc

    async def add_user(self, **fields: Any) -> dict[str, Any]:
        now = self.clock.now()
        doc = {
            "_id": new_id(), "email": "someone@example.org", "password_hash": _HASH,
            "name": "Someone", "phone": None, "time_zone": None, "theme": "system",
            "roles": ["client"], "org_id": ORG_A, "proposed_org_name": None, "status": "active",
            "rejection_reason": None, "last_login_at": None, "created_at": now,
            "updated_at": now, "created_by": None, "updated_by": None, "version": 1,
        }
        doc.update(fields)
        await self.db["users"].insert_one(doc)
        return doc


async def _seed(db: Any, now: datetime) -> None:
    for org_id, name in ((ORG_A, "Organization A"), (ORG_B, "Organization B")):
        await db["organizations"].insert_one({
            "_id": org_id, "name": name, "name_key": name.casefold(), "country": "JM",
            "contact_email": f"office@{name[-1].lower()}.example.org", "phone": "876 555 0100",
            "address": None, "status": "active", "created_at": now, "updated_at": now,
            "created_by": None, "updated_by": None, "version": 1,
        })
    for user in SEED_USERS.values():
        await db["users"].insert_one({
            "_id": user.id, "email": user.email, "password_hash": _HASH, "name": user.name,
            "phone": "876 555 0199", "time_zone": None, "theme": "system",
            "roles": list(user.roles), "org_id": user.org_id, "proposed_org_name": None,
            "status": user.status, "rejection_reason": None, "last_login_at": None,
            "created_at": now, "updated_at": now, "created_by": None, "updated_by": None,
            "version": 1,
        })


@pytest_asyncio.fixture
async def auth(mongo_uri, redis_url):
    # The clock starts at real time: Mongo's TTL monitor deletes by wall-clock time.
    clock = ManualClock(datetime.now(UTC))
    issuer = TestIssuer(clock)
    breached = Breached()
    db_name = f"auth_{uuid.uuid4().hex[:8]}"
    settings = Settings(
        mongo_uri=mongo_uri, mongo_db=db_name, redis_url=redis_url, run_background=False,
        app_url="https://mms.test", service_secrets={"platform": "platform-secret"},
        argon2_time_cost=1, argon2_memory_kib=1024, argon2_parallelism=1,
    )
    from redis.asyncio import Redis

    redis = Redis.from_url(redis_url)
    await redis.flushdb()
    mongo: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    await _seed(mongo[db_name], clock.now())
    # auth signs with the test issuer's key, so issuer tokens are real auth tokens.
    app = create_app(settings, ready_checks={}, clock=clock, signing_key=issuer.signing,
                     breached=breached)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
            harness = Auth(app, http, mongo[db_name], clock, issuer, redis, breached, settings)
            # The seed "disabled" user is refused like any disabled account.
            from mms_common.auth.revocation import revoke_user

            await revoke_user(redis, SEED_USERS["disabled"].id, clock.now())
            yield harness
            for c in harness.clients:
                await c.aclose()
    await mongo.drop_database(db_name)
    await mongo.close()
    await redis.aclose()
