"""operations test fixtures: the real app with its lifespan on throwaway Mongo and Redis, a
manual clock, tokens for the seed users (TP), operations' copy of organizations A and B, and
helpers to read the outbox."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest_asyncio
from mms_common.events import Envelope, validate
from mms_common.testing.seed import ORG_A, ORG_B, SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from pymongo import AsyncMongoClient

from app.config import Settings
from app.main import create_app

pytest_plugins = ["mms_common.testing.containers"]

BASE = "https://mms.test"
ORG_C = "01900000-0000-7000-8000-00000000c000"  # inactive


@dataclass
class Ops:
    app: Any
    http: httpx.AsyncClient
    db: Any
    clock: ManualClock
    issuer: TestIssuer

    def bearer(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issuer.token(who)}"}

    def service(self, name: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issuer.service_token(name)}"}

    async def outbox(self, type_: str | None = None) -> list[Envelope]:
        """Outbox rows, oldest first, each validated against its schema (contract check)."""
        query = {"type": type_} if type_ else {}
        cursor = self.db["outbox"].find(query).sort([("created_at", 1), ("_id", 1)])
        envelopes = []
        async for row in cursor:
            env = Envelope.model_validate(
                {k: v for k, v in row.items() if k not in ("_id", "created_at", "published_at")}
            )
            validate(env)
            envelopes.append(env)
        return envelopes

    async def station(self, who: str = "tech1", **fields: Any) -> dict[str, Any]:
        body = station_body(**fields)
        response = await self.http.post("/api/v1/stations", json=body, headers=self.bearer(who))
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()
        return data

    async def model(self, who: str = "tech1", **fields: Any) -> dict[str, Any]:
        body = {"kind": "sensor", "manufacturer": "Vaisala", "model": "HMP155",
                "parameters": ["AT", "RH"], "default_calibration_interval_days": 365, **fields}
        response = await self.http.post("/api/v1/sensor-models", json=body,
                                        headers=self.bearer(who))
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()
        return data

    async def unit(self, model_id: str, serial: str = "S-1", **fields: Any) -> dict[str, Any]:
        response = await self.http.post(
            "/api/v1/sensor-units", json={"model_id": model_id, "serial": serial, **fields},
            headers=self.bearer("tech1"),
        )
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()
        return data

    async def install(
        self, unit: dict[str, Any], station: dict[str, Any], parameter: str | None = "AT",
        **fields: Any,
    ) -> httpx.Response:
        return await self.http.post(
            f"/api/v1/sensor-units/{unit['id']}/install",
            json={"version": unit["version"], "station_id": station["id"],
                  "parameter": parameter, **fields},
            headers=self.bearer("tech1"),
        )


def station_body(**fields: Any) -> dict[str, Any]:
    return {
        "code": "JM-KIN-001", "name": "Kingston Harbour", "owner_org_id": ORG_A,
        "country": "JM", "time_zone": "America/Jamaica", "latitude": 17.97,
        "longitude": -76.79, "parameters": ["AT", "RH", "RAIN"], "type": "Synoptic",
        **fields,
    }


async def seed_orgs(db: Any) -> None:
    for org_id, name, country, status in (
        (ORG_A, "Organization A", "JM", "active"),
        (ORG_B, "Organization B", "TT", "active"),
        (ORG_C, "Closed Org", "BB", "inactive"),
    ):
        await db["organizations"].insert_one({
            "_id": org_id, "name": name, "name_key": name.casefold(), "country": country,
            "status": status, "aggregate_version": 1,
        })


@pytest_asyncio.fixture
async def ops(mongo_uri, redis_url):
    clock = ManualClock(datetime(2026, 10, 18, 12, 0, tzinfo=UTC))
    issuer = TestIssuer(clock)
    db_name = f"ops_{uuid.uuid4().hex[:8]}"
    settings = Settings(mongo_uri=mongo_uri, mongo_db=db_name, redis_url=redis_url,
                        run_background=False)
    mongo: AsyncMongoClient = AsyncMongoClient(mongo_uri)
    await seed_orgs(mongo[db_name])
    app = create_app(settings, ready_checks={}, clock=clock, keys=issuer.keys)
    async with app.router.lifespan_context(app):
        from mms_common.auth.revocation import revoke_user

        await revoke_user(app.state.redis, SEED_USERS["disabled"].id, clock.now())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as http:
            yield Ops(app, http, mongo[db_name], clock, issuer)
    await mongo.drop_database(db_name)
    await mongo.close()
