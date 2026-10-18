"""Reading, captioning and removing files (TRD §3.3). Which files a user can see is decided in
`repo.visible_to`; a file outside it does not exist for them (rule 4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, Forbidden, NotFound
from mms_common.ids import UUID7_PATTERN
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx, CtxDep
from app.api.schemas import CaptionIn, MediaDetail, MediaOut, MediaPage
from app.domain import media as rules
from app.domain.media import Status
from app.events.publish import Emitter
from app.repo import media as repo
from app.repo.storage import StorageError

router = APIRouter(prefix="/api/v1/media", tags=["media"])

Reader = Annotated[User, Depends(require_roles())]
Editor = Annotated[User, Depends(require_roles("technician", "admin", "client"))]
MediaId = Annotated[str, Path(pattern=UUID7_PATTERN)]


@router.get("")
async def list_media(
    user: Reader,
    ctx: CtxDep,
    owner_ref: Annotated[str, Query(min_length=3, max_length=200)],
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MediaPage:
    found = await repo.list_for_owner(ctx.svc.db, user, owner_ref, after, limit + 1)
    more = len(found) > limit
    found = found[:limit]
    return MediaPage(items=[MediaOut.of(d) for d in found],
                     next_after=found[-1]["_id"] if more else None)


def _url(ctx: Ctx, doc: dict[str, object], *, inline: bool) -> str:
    s = ctx.svc
    filename = str(doc["filename"])
    return s.storage.get_url(
        s.bucket(str(doc["kind"])), str(doc["original_key"]), s.settings.get_url_ttl_s,
        content_type=rules.content_type(filename),
        disposition=rules.disposition(filename, inline=inline),
    )


@router.get("/{media_id}")
async def get_media(media_id: MediaId, user: Reader, ctx: CtxDep) -> MediaDetail:
    """The file's record and, once it is `ready`, links to open and to download it (10 minutes;
    they act as a password, so they are never cached)."""
    doc = await repo.get_visible(ctx.svc.db, user, media_id)
    if doc is None:
        raise NotFound()
    urls: dict[str, str] = {}
    if doc["status"] == Status.READY.value:
        urls = {"view": _url(ctx, doc, inline=True), "download": _url(ctx, doc, inline=False)}
    return MediaDetail(**MediaOut.of(doc).model_dump(), urls=urls)


@router.patch("/{media_id}")
async def set_caption(media_id: MediaId, body: CaptionIn, user: Editor, ctx: CtxDep) -> MediaOut:
    """Uploader or staff who can write."""
    doc = await repo.get_visible(ctx.svc.db, user, media_id)
    if doc is None:
        raise NotFound()
    if doc["uploaded_by"] != user.id and not user.can_write:
        raise Forbidden()
    changed = await repo.set_caption(ctx.svc.db, media_id, body.caption, ctx.svc.clock.now())
    if changed is None:
        raise NotFound()
    return MediaOut.of(changed)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(media_id: MediaId, user: Editor, ctx: CtxDep) -> None:
    """Remove an upload that did not finish or did not pass its checks. A stored file is not
    deleted here: documents are kept with their versions, and configuration files can never
    be deleted (CFG-2). Visit photos and videos become deletable in Phase 4."""
    s = ctx.svc
    doc = await repo.get_visible(s.db, user, media_id)
    if doc is None:
        raise NotFound()
    if doc["uploaded_by"] != user.id and not user.is_admin:
        raise Forbidden()
    if doc["status"] not in (Status.PENDING.value, Status.FAILED.value):
        raise Conflict("A stored file can't be deleted", reason="immutable")
    if doc["status"] == Status.PENDING.value and doc.get("upload_id"):
        try:
            await s.storage.abort(s.bucket(doc["kind"]), doc["original_key"], doc["upload_id"])
        except StorageError:
            raise Conflict("Try again in a moment", reason="store_unavailable") from None
    emitter = Emitter(s.db, s.clock, ctx.actor(user), ctx.request_id)
    now = s.clock.now()
    expect = Status(doc["status"])

    async def body(session: AsyncClientSession) -> None:
        moved = await repo.transition(s.db, media_id, expect, Status.DELETED, now,
                                      changes={"deleted_at": now}, session=session)
        if moved is not None:
            await emitter.deleted(moved, session, doc)

    await in_transaction(s.client, body)
