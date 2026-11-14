"""The integrity check of the audit chain (PRD AUD-5, W19-4).

An admin queues a check from the audit log; the nightly run queues one too. One worker at a
time takes the oldest queued check (a Redis lock per tick, `claim_next` per check), reads the
chain in pages, and records `passed` or `broken` with the first bad record's number and nothing
else of its content. The result sets the gauge `audit_chain_ok` that the alerts of W20 watch,
and the check itself is recorded in the chain (W19-5).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from zoneinfo import ZoneInfo

from mms_common.ids import new_id
from mms_common.logging import get_logger
from mms_common.time import Clock
from prometheus_client import Gauge
from pymongo import AsyncMongoClient

from app.domain.audit_view import own_record
from app.repo import audit, audit_checks

log = get_logger(__name__)
Db = Any

chain_ok = Gauge(
    "audit_chain_ok", "1 when the last audit chain check passed, 0 when it broke",
    multiprocess_mode="livemostrecent",
)
SYSTEM: dict[str, Any] = {
    "user_id": None, "name": "System", "roles": [], "ip": None, "user_agent": None,
    "device_id": None,
}


async def run_next(
    *, db: Db, audit_client: AsyncMongoClient[dict[str, Any]], audit_db: Db, clock: Clock
) -> bool:
    """Take and run one queued check. False when there was none."""
    check = await audit_checks.claim_next(db, clock.now())
    if check is None:
        return False
    check_id = check["_id"]
    total, _ = await audit.head(audit_db)

    async def on_page(checked: int) -> None:
        await audit_checks.progress(db, check_id, checked=checked, total=total)

    try:
        broken = await audit.verify_paged(audit_db, on_page)
    except Exception as exc:  # noqa: BLE001 - recorded, and the next tick may take it again
        log.exception("audit_check_failed", check_id=check_id)
        await audit_checks.finish(db, check_id, status="failed", now=clock.now(), checked=0,
                                  total=total, error=type(exc).__name__)
        return True
    status = "passed" if broken is None else "broken"
    checked = total if broken is None else max(broken - 1, 0)
    await audit_checks.finish(db, check_id, status=status, now=clock.now(), checked=checked,
                              total=total, first_break_seq=broken)
    chain_ok.set(1 if broken is None else 0)
    try:
        by = check.get("requested_by") or {}
        actor = {**SYSTEM, **({"user_id": by.get("user_id"), "name": by.get("name"),
                              "roles": by.get("roles") or []} if by else {})}
        await audit.record_own(audit_client, audit_db, own_record(
            action="audit.verified", at=clock.now(), actor=actor, correlation_id=check_id,
            event_id=new_id(),
            metadata={"check_id": check_id, "kind": check["kind"], "result": status,
                      "records": total, "first_break_seq": broken},
        ))
    except Exception:  # noqa: BLE001 - the result stands even if the trace could not be written
        log.exception("audit_check_trace_failed", check_id=check_id)
    return True


async def schedule_nightly(db: Db, clock: Clock, tz: str, hour: int) -> bool:
    """Queue tonight's check once the hour has come in `tz`. The id is the date, so every
    instance and every tick of the day agrees on one."""
    local = clock.now().astimezone(ZoneInfo(tz))
    if local.hour < hour:
        return False
    return await audit_checks.create(
        db, check_id=f"nightly-{local.date().isoformat()}", kind="nightly", now=clock.now(),
        by=None,
    )


def make_tick(
    *, db: Db, audit_client: AsyncMongoClient[dict[str, Any]], audit_db: Db, clock: Clock,
    tz: str, hour: int,
) -> Callable[[], Awaitable[None]]:
    async def tick() -> None:
        await schedule_nightly(db, clock, tz, hour)
        while await run_next(db=db, audit_client=audit_client, audit_db=audit_db, clock=clock):
            pass

    return tick


__all__ = ["make_tick", "run_next", "schedule_nightly"]
