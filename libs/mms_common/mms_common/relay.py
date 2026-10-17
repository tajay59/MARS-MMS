"""The outbox relay's run loop (TRD §8.2), started from each producing service's lifespan.

Every worker runs this loop, but only the one holding the Redis leader lease publishes; it
opens a Kafka producer when it becomes leader and closes it when it loses the lease. A
change stream on `outbox` wakes the loop at once; without one it polls every second.
Kafka or Redis being down never stops the service: rows wait in the outbox and go out in
order when the broker returns (TP "Event backbone").
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pymongo.asynchronous.collection import AsyncCollection

from mms_common.logging import get_logger
from mms_common.outbox import LeaderLease, OutboxRelay, Produce
from mms_common.time import Clock

POLL_S = 1.0
ERROR_BACKOFF_S = 5.0

log = get_logger(__name__)


class Producer(Protocol):
    async def stop(self) -> None: ...


ProducerFactory = Callable[[], Awaitable[tuple[Producer, Produce]]]


async def run_relay(
    outbox: AsyncCollection[dict[str, Any]],
    lease: LeaderLease,
    open_producer: ProducerFactory,
    topic: str,
    clock: Clock,
    stop: asyncio.Event,
    *,
    batch_size: int = 100,
    poll_s: float = POLL_S,
    watch: bool = True,
) -> None:
    wake = asyncio.Event()
    watcher = asyncio.create_task(_watch(outbox, wake)) if watch else None
    producer: Producer | None = None
    relay: OutboxRelay | None = None
    try:
        while not stop.is_set():
            delay = poll_s
            try:
                if relay is None and await lease.acquire_or_renew():
                    producer, produce = await open_producer()
                    relay = OutboxRelay(outbox, lease, produce, topic, clock, batch_size)
                    log.info("outbox_leader", topic=topic)
                if relay is not None:
                    sent = await relay.run_once()
                    if not lease.held:
                        log.info("outbox_lease_lost", topic=topic)
                        await _close(producer)
                        producer, relay = None, None
                    elif sent >= batch_size:
                        delay = 0  # more waiting: carry on at once
            except Exception:  # noqa: BLE001 - Kafka or Redis unavailable: retry, keep serving
                log.exception("outbox_relay_failed", topic=topic)
                await _close(producer)
                producer, relay = None, None
                delay = ERROR_BACKOFF_S
            if delay:
                wake.clear()
                await _wait_any(stop, wake, delay)
    finally:
        if watcher is not None:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        await _close(producer)
        with contextlib.suppress(Exception):
            await lease.release()


async def _close(producer: Producer | None) -> None:
    if producer is not None:
        with contextlib.suppress(Exception):
            await producer.stop()


async def _wait_any(stop: asyncio.Event, wake: asyncio.Event, seconds: float) -> None:
    waits = [asyncio.create_task(stop.wait()), asyncio.create_task(wake.wait())]
    try:
        await asyncio.wait(waits, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in waits:
            task.cancel()


async def _watch(outbox: AsyncCollection[dict[str, Any]], wake: asyncio.Event) -> None:
    """Set `wake` on every insert. Falls back to polling alone if the stream fails."""
    while True:
        try:
            async with await outbox.watch([{"$match": {"operationType": "insert"}}]) as stream:
                async for _ in stream:
                    wake.set()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - e.g. no changeStream privilege: polling still works
            log.warning("outbox_watch_failed")
            await asyncio.sleep(30)
