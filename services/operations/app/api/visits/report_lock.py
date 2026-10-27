"""Locking a visit for its report (VIS-12; TRD 11.2; W17-8). Called by the report service.

Each call is one transaction on the visit. The rules (`domain.visits.lock`) say what changes; a
repeat of the same call changes nothing and so writes nothing, which keeps a retried finalize from
bumping the visit's version. The visit's version after the call is the board as it was locked.
"""

from __future__ import annotations

from typing import Any

from mms_common.errors import NotFound

from app.api.context import Ctx
from app.domain.visits import lock as rules
from app.repo.visits import visits as visit_repo


async def lock(
    ctx: Ctx, visit_id: str, report_id: str, version: int
) -> tuple[dict[str, Any], bool]:
    async def body(s: Any) -> tuple[dict[str, Any], bool]:
        visit = await visit_repo.get(ctx.db, visit_id, None, s)
        if visit is None:
            raise NotFound()
        change = rules.lock(visit, report_id, version, ctx.clock.now())
        if change.fields:
            visit = await visit_repo.update(ctx.db, visit_id, change.fields, now=ctx.clock.now(),
                                            by=None, session=s)
        return visit, change.locked

    return await ctx.tx(body)


async def unlock(
    ctx: Ctx, visit_id: str, report_id: str, version: int
) -> tuple[dict[str, Any], bool]:
    async def body(s: Any) -> tuple[dict[str, Any], bool]:
        visit = await visit_repo.get(ctx.db, visit_id, None, s)
        if visit is None:
            raise NotFound()
        change = rules.unlock(visit, report_id, version)
        if change.fields:
            visit = await visit_repo.update(ctx.db, visit_id, change.fields, now=ctx.clock.now(),
                                            by=None, session=s)
        return visit, change.locked

    return await ctx.tx(body)
