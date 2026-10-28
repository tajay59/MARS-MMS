"""Reminders that a visit report is not finalized (PRD RPT-7; W17-11): `tick` runs hourly under a
Redis lock (`mms_common.cron`). A draft whose 2nd or 5th working day has come, and that has not
been reminded at that level, adds `report.finalize_reminder` to the outbox in the same transaction
that marks it. Platform decides who hears: at 2 days the people who have not signed (the lead
when everyone has), at 5 days the admins too. A reopened version starts counting again.
"""

from __future__ import annotations

from typing import Any

from mms_common.logging import get_logger
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import reminders
from app.events import publish
from app.repo import reports, signatures
from app.services import Services

log = get_logger(__name__)


async def tick(svc: Services) -> dict[str, int]:
    done = {"checked": 0, "sent": 0}
    now = svc.clock.now()
    for report in await reports.reminder_candidates(svc.db):
        done["checked"] += 1
        due = reminders.due_levels(report, now)
        if not due:
            continue
        level, marked = reminders.reminder_levels(due)
        signed = await signatures.valid(svc.db, report["_id"], report["version"])
        who = reminders.recipients(report, {s["signer_id"] for s in signed})

        async def save(
            session: AsyncClientSession, report: dict[str, Any] = report, level: int = level,
            marked: list[int] = marked, who: list[str] = who,
        ) -> bool:
            if not await reports.mark_reminded(svc.db, report["_id"], marked, level, now, session):
                return False
            await publish.finalize_reminder(
                svc.db, svc.clock, report, working_days=level, staff_ids=who, session=session)
            return True

        if await in_transaction(svc.client, save):
            done["sent"] += 1
            log.info("finalize_reminder", report_id=report["_id"], working_days=level)
    return done
