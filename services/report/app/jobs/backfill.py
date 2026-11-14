"""Build the read model from operations' snapshots (TRD §8.6).

Read models are rebuilt from current state, never by replaying the outbox. Each item goes
through the same `aggregate_version` guard as the events, so running this again, or while events
arrive, changes nothing it should not. `python -m app.cli backfill` runs it by hand; the report
service runs it once at every start, because its consumer group begins at the oldest event Kafka
still holds and the read model covers everything entered since Phase 2.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mms_common.logging import get_logger
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import readmodel as rm
from app.repo import readmodel
from app.repo.operations import OperationsUnavailable, SnapshotSource

log = get_logger(__name__)


async def backfill(
    db: AsyncDatabase[dict[str, Any]], source: SnapshotSource
) -> dict[str, tuple[int, int]]:
    """Returns, for each entity, `(read, written)`: how many items operations sent and how
    many were newer than what the read model held."""
    counts: dict[str, tuple[int, int]] = {}
    for entity, (collection, build) in rm.SNAPSHOT_ENTITIES.items():
        read = written = 0
        after: str | None = None
        while True:
            items, after = await source.snapshot(entity, after)
            for item in items:
                version = int(item.pop("aggregate_version"))
                read += 1
                if await readmodel.put(db, collection, build(item, version)):
                    written += 1
            if not after:
                break
        counts[entity] = (read, written)
    return counts


async def run(
    db: AsyncDatabase[dict[str, Any]], source: SnapshotSource, stop: asyncio.Event,
    retry_s: float = 5.0,
) -> None:
    """Retries until operations answers (it may still be starting), then stops."""
    while not stop.is_set():
        try:
            counts = await backfill(db, source)
        except (OperationsUnavailable, KeyError, ValueError) as exc:
            log.warning("read_model_backfill_failed", error=f"{type(exc).__name__}: {exc}"[:300])
        else:
            log.info("read_model_backfill_done", **{k: v[0] for k, v in counts.items()})
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=retry_s)
        except TimeoutError:
            continue
