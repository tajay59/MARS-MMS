"""The weekly calibration digest (PRD CAL-5, NOT-1, Appendix B "Calibrations due"; W9-14).

Every Monday at `digest_hour` in `digest_tz` the admins get an in-app notification, and an email
unless they turned it off, listing the sensors that are overdue or due within 30 days. The list
comes from operations' `/internal/calibrations/due` with platform's service token (rule 1).

The job wakes every hour. It sends for the current ISO week if that week's Monday time has
passed and no `digest_runs` document exists for it yet. That makes it safe to restart, to run on
every instance (the Redis cron lock is only a courtesy) and to catch up after downtime within
the week. Nothing due means no digest, and the week is still marked done.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
from mms_common.auth.service_client import ServiceTokens
from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app import realtime
from app.domain import notification_emails as copy
from app.domain.account_emails import EmailJob, Kind
from app.domain.notifications import Draft
from app.repo import digests, directory, emails, notifications

log = get_logger(__name__)


def week_due(now: datetime, tz: str, hour: int) -> str | None:
    """`2026-W43` when this ISO week's Monday `hour` (local time in `tz`) has come, else None."""
    local = now.astimezone(ZoneInfo(tz))
    year, week, _ = local.isocalendar()
    monday = datetime.fromisocalendar(year, week, 1).replace(hour=hour, tzinfo=local.tzinfo)
    return f"{year}-W{week:02d}" if local >= monday else None


def digest_items(due: Sequence[Mapping[str, Any]], tz: str) -> list[dict[str, Any]]:
    """What the emails need from operations' list: state, place, sensor and the date in words."""
    zone = ZoneInfo(tz)
    out: list[dict[str, Any]] = []
    for unit in due:
        at = datetime.fromisoformat(str(unit["calibration_due_at"])).astimezone(zone)
        station = unit.get("station") or {}
        model = unit.get("model") or {}
        out.append({
            "unit_id": unit["unit_id"], "serial": unit["serial"],
            "model": f"{model.get('manufacturer', '')} {model.get('model', '')}".strip()
            or "Sensor",
            "station_code": station.get("code"), "due_state": unit["due_state"],
            "due_label": f"{at.day} {at:%b}", "due_at": at.isoformat(),
        })
    return out


class OperationsApi(Protocol):
    async def due(self, within_days: int) -> list[dict[str, Any]]: ...


class OperationsClient:
    def __init__(self, base_url: str, tokens: ServiceTokens, http: httpx.AsyncClient) -> None:
        self._base, self._tokens, self._http = base_url.rstrip("/"), tokens, http

    async def due(self, within_days: int) -> list[dict[str, Any]]:
        response = await self._http.get(
            f"{self._base}/internal/calibrations/due", params={"within_days": within_days},
            headers=await self._tokens.headers(), timeout=15,
        )
        response.raise_for_status()
        items: list[dict[str, Any]] = response.json()["items"]
        return items


async def send_digest(
    *, client: AsyncMongoClient[dict[str, Any]], db: AsyncDatabase[dict[str, Any]],
    redis: Redis | None, operations: OperationsApi, clock: Clock, tz: str, hour: int,
    within_days: int,
) -> str | None:
    """Send this week's digest if it is time and it has not gone out. Returns the week sent
    for, or None when there was nothing to do."""
    now = clock.now()
    week = week_due(now, tz, hour)
    if week is None or await digests.get(db, week) is not None:
        return None
    items = digest_items(await operations.due(within_days), tz)
    pushes: list[tuple[str, dict[str, Any]]] = []

    async def body(session: AsyncClientSession) -> bool:
        if not await digests.claim(db, week, now, items, within_days, session):
            return False
        if not items:
            return True
        counts = copy.digest_counts(items)
        who = await directory.audience(db, None, session)
        drafts = [
            Draft(
                user_id=admin, type="calibration.digest", title=copy.digest_title(counts),
                body=copy.digest_body(counts, within_days), link="/calibration",
                entity_type="calibration", entity_id=week, email=True,
            )
            for admin in who.admins
        ]
        rows = await notifications.insert_many(db, drafts, f"digest:{week}", now, session)
        for row in rows:
            await emails.enqueue(
                db, f"{row['_id']}", EmailJob(Kind.DIGEST, row["user_id"], digest_id=week,
                                              notification_id=row["_id"]),
                now, session,
            )
            pushes.append((row["user_id"], realtime.notification_message(row)))
        return True

    claimed = await in_transaction(client, body)
    if claimed and redis is not None:
        await realtime.publish(redis, pushes)
    if claimed:
        log.info("calibration_digest", week=week, units=len(items), notified=len(pushes))
    return week if claimed else None


def make_tick(**kwargs: Any) -> Callable[[], Any]:
    async def tick() -> None:
        await send_digest(**kwargs)

    return tick
