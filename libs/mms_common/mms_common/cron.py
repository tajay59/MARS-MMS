"""Scheduled jobs: one run at a time per job across every worker and container (TRD §9).

Each instance wakes on the interval and tries `SET cron:<service>:<job> NX PX`; only the
one that gets the lock runs the job for that interval.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from mms_common.ids import new_id
from mms_common.logging import get_logger

log = get_logger(__name__)


class LockStore(Protocol):
    def set(self, name: str, value: str, *, nx: bool, px: int) -> Awaitable[Any]: ...


def lock_key(service: str, job: str) -> str:
    return f"cron:{service}:{job}"


async def run_once_locked(
    store: LockStore, service: str, job: str, every_s: float, body: Callable[[], Awaitable[Any]]
) -> bool:
    """Run `body` if no other instance has run this job in the current interval."""
    got = await store.set(lock_key(service, job), new_id(), nx=True, px=int(every_s * 1000 * 0.9))
    if not got:
        return False
    try:
        await body()
    except Exception:  # noqa: BLE001 - a failed run is logged and retried next interval
        log.exception("cron_failed", job=job)
    return True


async def run_periodic(
    store: LockStore,
    service: str,
    job: str,
    every_s: float,
    body: Callable[[], Awaitable[Any]],
    stop: asyncio.Event,
    first_delay_s: float = 30.0,
) -> None:
    delay = first_delay_s
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            return
        except TimeoutError:
            pass
        try:
            await run_once_locked(store, service, job, every_s, body)
        except Exception:  # noqa: BLE001 - Redis unreachable: try again next interval
            log.exception("cron_lock_failed", job=job)
        delay = every_s
