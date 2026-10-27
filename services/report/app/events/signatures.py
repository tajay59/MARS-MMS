"""Clearing signatures when a draft changes (TRD 11.2 step 3; W17-3, W17-4), in the transaction
of the change, with `report.signatures_cleared` through the outbox (rule 2).

Called by an edit (`reason="edit"`, the person's actor) and by a facts refresh that changed what
prints (`reason="facts"`, the system's). Nothing is deleted: the signatures stay, flagged.
"""

from __future__ import annotations

from typing import Any

from mms_common.events import Actor
from mms_common.time import Clock
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.events import publish
from app.repo import signatures


async def clear(
    db: AsyncDatabase[dict[str, Any]], clock: Clock, report: dict[str, Any], *, reason: str,
    by: str, actor: Actor, session: AsyncClientSession,
) -> int:
    """Clear the report version's valid signatures and say so. Returns how many there were
    (zero writes no event)."""
    count = await signatures.clear(
        db, report["_id"], report["version"], by=by, now=clock.now(), session=session)
    if count:
        await publish.signatures_cleared(
            db, clock, report, count=count, reason=reason, actor=actor, session=session)
    return count
