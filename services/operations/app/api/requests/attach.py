"""Checking the files a request or comment is about to hold (PRD REQ-3; W9-8)."""

from __future__ import annotations

from typing import Any

from mms_common.auth import User
from mms_common.errors import Conflict

from app.api.context import Ctx
from app.domain.requests import comments as rules
from app.repo.requests import comments as repo


class FileInUse(Conflict):
    code, title = "file_in_use", "That file is already attached to something else"


async def verified(
    ctx: Ctx, user: User, owner: str, media_ids: list[str]
) -> list[dict[str, Any]]:
    """Each file is a clean PDF this person uploaded for `owner`, not used before. Returns the
    entries to keep on the request or comment."""
    kept: list[dict[str, Any]] = []
    for media_id in media_ids:
        facts = rules.check_attachment(
            await repo.file_facts(ctx.media, media_id, ctx.request_id),
            owner=owner, user_id=user.id,
        )
        if await repo.media_in_use(ctx.db, media_id):
            raise FileInUse()
        kept.append({"media_id": media_id, "name": facts.filename, "size_bytes": facts.size_bytes})
    return kept
