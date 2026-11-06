"""Seed the volume the load test runs against (TRD §17, PRD NFR-1; W20 slice 6): by default five times
the demo data, 250 stations, 1,000 requests and 500 visits, made through the real API as the seed users,
so every row went through validation, the outbox and the consumers.

    python infra/loadtest/seed_volume.py                       # the local stack
    python infra/loadtest/seed_volume.py --stations 25 --requests 100 --visits 50

THIS IS FOR A THROWAWAY STACK. It refuses any host that is not local unless the operator names
that host in LOAD_ALLOW_HOST, which is the production host before go-live, wiped afterwards
(plan decision 11). Run auth's `seed` and operations' `seed` first (the seed users and the two
demo organizations must exist). Safe to run again: stations are skipped by code; requests and
visits are added each time.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from common import EMAILS, HOST, ORG_A, ORG_B, PASSWORD, base_url, host_header, uuid7

PREFIX = "LT"
CATEGORIES = [
    "fault",
    "communications",
    "power",
    "calibration",
    "relocation",
    "inspection",
    "other",
]


def refuse_unless_throwaway() -> None:
    local = (
        HOST == "localhost"
        or HOST.endswith(".localhost")
        or HOST in ("127.0.0.1", "::1")
    )
    if local or os.environ.get("LOAD_ALLOW_HOST") == HOST:
        return
    sys.exit(
        f"refusing to seed {HOST}: it is not a local stack. If this is a throwaway stack on purpose "
        f"(the production host before go-live, to be wiped), set LOAD_ALLOW_HOST={HOST}."
    )


class Api:
    def __init__(self) -> None:
        self.http = httpx.AsyncClient(
            base_url=base_url(), headers=host_header(), verify=False, timeout=60
        )
        self.tokens: dict[str, str] = {}
        self.calls = 0

    async def login(self, who: str) -> str:
        for attempt in range(40):
            r = await self.http.post(
                "/api/v1/auth/login", json={"email": EMAILS[who], "password": PASSWORD}
            )
            if (
                r.status_code == 429
            ):  # the gateway allows ten logins a minute per address
                await asyncio.sleep(7 + attempt % 3)
                continue
            r.raise_for_status()
            self.tokens[who] = r.json()["access_token"]
            return self.tokens[who]
        raise RuntimeError(f"could not sign in as {who}")

    async def call(self, who: str, method: str, path: str, **kw: Any) -> httpx.Response:
        for attempt in range(60):
            r = await self.http.request(
                method,
                path,
                headers={"Authorization": f"Bearer {self.tokens[who]}"},
                **kw,
            )
            self.calls += 1
            if r.status_code == 429:  # 300 a minute per user: wait, do not fail
                await asyncio.sleep(1 + min(attempt, 5))
                continue
            if r.status_code == 401:
                await self.login(who)
                continue
            return r
        raise RuntimeError(f"{method} {path} kept answering 429")

    async def close(self) -> None:
        await self.http.aclose()


async def gather_limited(jobs: list[Any], limit: int) -> list[Any]:
    gate = asyncio.Semaphore(limit)

    async def run(job: Any) -> Any:
        async with gate:
            return await job

    return await asyncio.gather(*(run(j) for j in jobs))


async def make_stations(api: Api, count: int) -> dict[str, list[str]]:
    """Station ids by organization, creating LT-0001... as needed."""
    existing = await api.call(
        "admin", "GET", "/api/v1/stations", params={"q": f"{PREFIX}-", "limit": 500}
    )
    by_code = {s["code"]: s for s in existing.json()["items"]}
    rng = random.Random(7)

    async def one(n: int) -> dict[str, Any]:
        code = f"{PREFIX}-{n:04d}"
        if code in by_code:
            return by_code[code]
        org = ORG_A if n % 2 else ORG_B
        r = await api.call(
            "admin",
            "POST",
            "/api/v1/stations",
            json={
                "code": code,
                "name": f"Load test station {n}",
                "country": "JM",
                "time_zone": "America/Jamaica",
                "owner_org_id": org,
                "status": "operational",
                "latitude": round(17.6 + rng.random() * 1.2, 5),
                "longitude": round(-78.4 + rng.random() * 2.0, 5),
            },
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"station {code}: {r.status_code} {r.text[:200]}")
        return r.json()

    made = await gather_limited([one(n) for n in range(1, count + 1)], 6)
    out: dict[str, list[str]] = {ORG_A: [], ORG_B: []}
    for s in made:
        out[s["owner_org_id"]].append(s["id"])
    return out


async def main(args: argparse.Namespace) -> None:
    refuse_unless_throwaway()
    api = Api()
    try:
        for who in ("admin", "tech1", "tech2", "client_a1", "client_b1"):
            await api.login(who)
        techs = []
        for who in ("tech1", "tech2"):
            me = await api.call(who, "GET", "/api/v1/auth/me")
            techs.append(me.json()["id"])

        print(f"stations: {args.stations}")
        stations = await make_stations(api, args.stations)
        print(
            f"  {sum(map(len, stations.values()))} stations ({len(stations[ORG_A])} for A, {len(stations[ORG_B])} for B)"
        )

        print(f"requests: {args.requests}")
        rng = random.Random(11)

        async def new_request(n: int) -> tuple[str, str, str]:
            org, who = (ORG_A, "client_a1") if n % 2 else (ORG_B, "client_b1")
            station = stations[org][n // 2 % len(stations[org])]
            request_id = uuid7()
            r = await api.call(
                who,
                "POST",
                "/api/v1/requests",
                json={
                    "id": request_id,
                    "title": f"[Load] request {n}",
                    "description": "Made by the load test seeder.",
                    "category": rng.choice(CATEGORIES),
                    "priority": "normal",
                    "station_ids": [station],
                },
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"request {n}: {r.status_code} {r.text[:200]}")
            return request_id, org, station

        made = await gather_limited([new_request(n) for n in range(args.requests)], 6)

        approved = made[: int(len(made) * 0.7)]
        print(f"approving {len(approved)}")
        await gather_limited(
            [
                api.call("admin", "POST", f"/api/v1/requests/{rid}/approve")
                for rid, _, _ in approved
            ],
            6,
        )

        visits = min(args.visits, len(approved))
        print(f"assigning and scheduling {visits} visits")
        start = datetime.now(UTC).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

        async def visit(i: int) -> None:
            rid, _, station = approved[i]
            tech = techs[i % 2]
            r = await api.call(
                "admin",
                "POST",
                f"/api/v1/requests/{rid}/assign",
                json={"staff_ids": [tech]},
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"assign {rid}: {r.status_code} {r.text[:200]}")
            when = start + timedelta(hours=i % 200)
            r = await api.call(
                "admin",
                "POST",
                "/api/v1/visits",
                json={
                    "id": uuid7(),
                    "request_id": rid,
                    "staff_ids": [tech],
                    "lead_staff_id": tech,
                    "planned_start": when.isoformat().replace("+00:00", "Z"),
                    "planned_end": (when + timedelta(hours=2))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "stations": [{"station_id": station, "owner_staff_id": tech}],
                },
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"visit {i}: {r.status_code} {r.text[:200]}")

        await gather_limited([visit(i) for i in range(visits)], 6)
        print(f"done: {api.calls} calls")
    finally:
        await api.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stations", type=int, default=250)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--visits", type=int, default=500)
    asyncio.run(main(parser.parse_args()))
