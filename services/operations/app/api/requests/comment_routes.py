"""Comments and attachments on a request (PRD REQ-3, REQ-9, REQ-10; AFD J3 step 5; TRD §3.2).

A flat thread, oldest first. Staff may mark a comment internal: it is never shown to a client,
and neither are its files (rule 6). The filter lives in `repo/requests/comments.py`; the files
are shown to the organization by `media.visibility_requested` in the transaction that attaches
them, and a client reaches one only through the download routes here, which look the comment
up as that client first (ADR-19).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, NotFound
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import CtxDep
from app.api.requests.attach import verified
from app.api.requests.request_routes import require_who
from app.api.requests.schemas import CommentIn, CommentOut, CommentPage, CommentPatch
from app.api.stations.doc_schemas import DownloadOut
from app.domain.requests import comments as rules
from app.events.publish import ev
from app.repo.requests import comments as repo
from app.repo.requests import requests as request_repo
from app.repo.stations.common import stamp

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])

Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client their own org
Poster = Annotated[User, Depends(require_roles("client", "technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
MediaPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


@router.get("/{id}/comments")
async def list_comments(id: IdPath, viewer: Reader, ctx: CtxDep) -> CommentPage:
    """REQ-9, REQ-10: oldest first. A client gets no internal comments, and so no trace of them."""
    await request_repo.require(ctx.db, id, viewer)
    now = ctx.clock.now()
    return CommentPage(
        items=[CommentOut.of(d, viewer, now) for d in await repo.thread(ctx.db, id, viewer)]
    )


@router.post("/{id}/comments", status_code=status.HTTP_201_CREATED)
async def post_comment(
    id: IdPath, body: CommentIn, response: Response, user: Poster, ctx: CtxDep
) -> CommentOut:
    """REQ-9. Idempotent by `id`: a retry after a lost answer returns the comment already
    posted (200). Files must already be clean (the page waits), and go to the organization
    with the comment, or stay staff-only if the comment is internal."""
    request = await request_repo.require(ctx.db, id, user)
    who = require_who(user)
    now = ctx.clock.now()
    comment_id = body.id or new_id()
    existing = await repo.get(ctx.db, id, comment_id)
    if existing is not None:
        if existing["author_id"] != user.id:
            raise Conflict("That ID is already used", code="id_taken")
        response.status_code = status.HTTP_200_OK
        return CommentOut.of(existing, user, now)

    text = rules.clean_body(body.body)
    internal = rules.is_internal(body.internal, who)
    media_ids = rules.check_media_ids(body.media_ids)
    attachments = await verified(ctx, user, rules.comment_owner_ref(id, comment_id), media_ids)
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        doc = stamp({
            "_id": comment_id, "request_id": id, "org_id": request["org_id"],
            "author_id": user.id, "author_name": user.name, "author_role": rules.role_of(who),
            "body": text, "internal": internal, "attachments": attachments, "edited_at": None,
        }, now, user.id)
        await repo.insert(ctx.db, doc, s)
        await emitter.comment(ev.CommentAdded, "comment.added", doc, request, s)
        if attachments:
            await emitter.attachments_visibility(
                "comment", doc, request, media_ids, "staff" if internal else "org", s
            )
        return doc

    try:
        doc = await ctx.tx(save)
    except DuplicateKeyError:
        # The same `id` arrived twice at once: the other one won. Hand back what it made.
        won = await repo.get(ctx.db, id, comment_id)
        if won is None or won["author_id"] != user.id:
            raise Conflict("That ID is already used", code="id_taken") from None
        response.status_code = status.HTTP_200_OK
        return CommentOut.of(won, user, now)
    return CommentOut.of(doc, user, now)


@router.patch("/{id}/comments/{comment_id}")
async def edit_comment(
    id: IdPath, comment_id: IdPath, body: CommentPatch, user: Poster, ctx: CtxDep
) -> CommentOut:
    """REQ-9, REQ-10: the author changes the text within 15 minutes; staff may also mark their
    comment internal (or not). Making it internal hides its files from the client again."""
    request = await request_repo.require(ctx.db, id, user)
    current = await repo.require(ctx.db, id, comment_id, user)
    now = ctx.clock.now()
    rules.check_can_edit(current["author_id"], current["created_at"], user.id, now)
    who = require_who(user)

    changes: dict[str, Any] = {}
    if body.body is not None:
        text = rules.clean_body(body.body)
        if text != current["body"]:
            changes.update(body=text, edited_at=now)
    if body.internal is not None and who.value != "client":
        if body.internal != current["internal"]:
            changes["internal"] = body.internal
    if not changes:
        if body.version != current["version"]:
            raise Conflict("The comment changed. Reload and try again", code="version_conflict")
        return CommentOut.of(current, user, now)
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await repo.update(ctx.db, comment_id, changes, now=now, by=user.id,
                                    expected_version=body.version, session=s)
        await emitter.comment(
            ev.CommentUpdated, "comment.updated", updated, request, s, before=current,
            body_changed="body" in changes, internal_changed="internal" in changes,
        )
        if "internal" in changes and updated["attachments"]:
            await emitter.attachments_visibility(
                "comment", updated, request, [a["media_id"] for a in updated["attachments"]],
                "staff" if updated["internal"] else "org", s,
            )
        return updated

    return CommentOut.of(await ctx.tx(save), user, now)


async def _download(
    ctx: Any, attachments: list[dict[str, Any]], media_id: str
) -> DownloadOut:
    """A ten-minute link for a file the person was allowed to find, once media has cleared it."""
    entry = next((a for a in attachments if a["media_id"] == media_id), None)
    if entry is None:
        raise NotFound()
    info = await ctx.media.info(media_id, ctx.request_id)
    if info is None:
        raise NotFound()
    if info.status != "ready":
        raise Conflict("The file is still being checked", code="not_ready")
    link = await ctx.media.link(media_id, inline=True, request_id=ctx.request_id)
    return DownloadOut(url=link.url, expires_at=link.expires_at, filename=entry["name"])


@router.get("/{id}/attachments/{media_id}/download")
async def download_request_file(
    id: IdPath, media_id: MediaPath, viewer: Reader, ctx: CtxDep
) -> DownloadOut:
    request = await request_repo.require(ctx.db, id, viewer)
    return await _download(ctx, request.get("attachments", []), media_id)


@router.get("/{id}/comments/{comment_id}/attachments/{media_id}/download")
async def download_comment_file(
    id: IdPath, comment_id: IdPath, media_id: MediaPath, viewer: Reader, ctx: CtxDep
) -> DownloadOut:
    """A client asking for an internal comment's file gets 404, as if it did not exist."""
    await request_repo.require(ctx.db, id, viewer)
    comment = await repo.require(ctx.db, id, comment_id, viewer)
    return await _download(ctx, comment["attachments"], media_id)
