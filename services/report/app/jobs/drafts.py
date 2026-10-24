"""Keeping visit report drafts up to date (TRD 3.4, 11.2; W16-2, W16-4, W16-5).

`tick` runs about every half minute under a Redis lock (`mms_common.cron`):

1. A draft whose board changed (or that was just made) has its facts read from operations and the
   state of each of its files from media. The narrative is pre-filled once and never rewritten.
2. A draft still waiting for files has them looked at again.
3. A draft with its facts and no PDF yet is drawn the first time when every file is processed, or
   five minutes after the visit ended, whichever comes first (the exit criterion is ten).

Every step is safe to repeat. An unreachable service leaves the draft as it was for the next tick.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from mms_common.logging import get_logger

from app.domain import drafts
from app.repo import reports
from app.repo.operations import OperationsUnavailable
from app.services import Services

log = get_logger(__name__)

STATUS_AT_ONCE = 8  # files asked about at once


def job_id(report_id: str) -> str:
    return f"draft:{report_id}"


async def _statuses(svc: Services, facts: dict[str, Any]) -> dict[str, str | None]:
    ids = list(dict.fromkeys(r["media_id"] for r in drafts.media_refs(facts)))
    gate = asyncio.Semaphore(STATUS_AT_ONCE)

    async def one(media_id: str) -> tuple[str, str | None]:
        async with gate:
            return media_id, await svc.media.status(media_id)

    return dict(await asyncio.gather(*(one(i) for i in ids)))


async def refresh_facts(svc: Services, report: dict[str, Any]) -> bool:
    """Read the board again. False when a service did not answer (the draft stays stale)."""
    try:
        facts = await svc.facts.visit_facts(report["visit_id"])
        if facts is None:
            log.warning("draft_visit_unknown", report_id=report["_id"])
            return False
        statuses = await _statuses(svc, facts)
    except OperationsUnavailable:
        return False
    content = report["content"]
    first = content["narrative"] is None
    narrative = drafts.default_narrative(facts) if first else None
    selection = (
        drafts.default_media_selection(facts) if first
        else drafts.refreshed_selection(content["media_selection"], facts)
    )
    await reports.set_facts(
        svc.db, report["_id"], expected_stale_at=report["facts_stale_at"], facts=facts,
        narrative=narrative, selection=selection,
        awaiting=drafts.pending_media(facts, statuses), now=svc.clock.now(),
    )
    return True


async def look_at_waiting(svc: Services, report: dict[str, Any]) -> None:
    facts = report["content"]["facts"]
    if facts is None:
        return
    try:
        statuses = await _statuses(svc, facts)
    except OperationsUnavailable:
        return
    await reports.set_awaiting(
        svc.db, report["_id"], drafts.pending_media(facts, statuses), svc.clock.now())


async def tick(svc: Services) -> dict[str, int]:
    """One round. Returns what it did, for the log and the tests."""
    done = {"refreshed": 0, "queued": 0}
    for report in await reports.stale_drafts(svc.db):
        if await refresh_facts(svc, report):
            done["refreshed"] += 1
    for report in await reports.waiting_for_media(svc.db):
        await look_at_waiting(svc, report)
    wait = timedelta(seconds=svc.settings.draft_wait_s)
    for report in await reports.due_for_first_pdf(svc.db):
        if drafts.ready_to_render(report, svc.clock.now(), wait) and await reports.request_render(
            svc.db, report["_id"], svc.clock.now()
        ):
            await svc.jobs.enqueue(job_id(report["_id"]))
            done["queued"] += 1
    return done
