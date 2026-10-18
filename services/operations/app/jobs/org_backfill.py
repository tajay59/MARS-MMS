"""Backfill operations' copy of the organizations from auth's snapshot (TRD §8.6).

Runs at startup, because the `operations` consumer group starts at the oldest event Kafka
still holds (14 days) and organizations can be older. Each page goes through the same
`aggregate_version` guard as the events, so running it again changes nothing.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.logging import get_logger
from pymongo.asynchronous.database import AsyncDatabase

from app.events.org_consumer import apply_org

log = get_logger(__name__)


async def backfill_orgs(
    db: AsyncDatabase[dict[str, Any]],
    http: httpx.AsyncClient,
    tokens: ServiceTokens,
    auth_url: str,
) -> int:
    """Returns the number of organizations read."""
    url = auth_url.rstrip("/") + "/internal/snapshot/organizations"
    after: str | None = None
    count = 0
    while True:
        params: dict[str, Any] = {"limit": 500}
        if after:
            params["after"] = after
        response = await http.get(url, params=params, headers=await tokens.headers(), timeout=10)
        response.raise_for_status()
        body = response.json()
        for item in body["items"]:
            version = int(item.pop("aggregate_version"))
            await apply_org(db, item, version)
            count += 1
        after = body.get("next_after")
        if not after:
            return count


async def run(
    db: AsyncDatabase[dict[str, Any]],
    http: httpx.AsyncClient,
    tokens: ServiceTokens,
    auth_url: str,
    stop: asyncio.Event,
    retry_s: float = 5.0,
) -> None:
    """Retries until auth answers (it may still be starting), then stops."""
    while not stop.is_set():
        try:
            count = await backfill_orgs(db, http, tokens, auth_url)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("org_backfill_failed", error=f"{type(exc).__name__}: {exc}"[:300])
        else:
            log.info("org_backfill_done", organizations=count)
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=retry_s)
        except TimeoutError:
            continue
