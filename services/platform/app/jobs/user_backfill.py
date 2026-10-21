"""Backfill the user directory from auth's snapshot (TRD §8.6): at start, because the
`notification` consumer group begins at the oldest event Kafka still holds and people can be
older. The `aggregate_version` guard makes running it again change nothing."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.logging import get_logger
from pymongo.asynchronous.database import AsyncDatabase

from app.repo import directory

log = get_logger(__name__)


async def backfill_users(
    db: AsyncDatabase[dict[str, Any]], http: httpx.AsyncClient, tokens: ServiceTokens,
    auth_url: str,
) -> int:
    url = auth_url.rstrip("/") + "/internal/snapshot/users"
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
            await directory.upsert(db, item, version)
            count += 1
        after = body.get("next_after")
        if not after:
            return count


async def run(
    db: AsyncDatabase[dict[str, Any]], http: httpx.AsyncClient, tokens: ServiceTokens,
    auth_url: str, stop: asyncio.Event, retry_s: float = 5.0,
) -> None:
    """Retries until auth answers (it may still be starting), then stops."""
    while not stop.is_set():
        try:
            count = await backfill_users(db, http, tokens, auth_url)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("user_backfill_failed", error=f"{type(exc).__name__}: {exc}"[:300])
        else:
            log.info("user_backfill_done", users=count)
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=retry_s)
        except TimeoutError:
            continue
