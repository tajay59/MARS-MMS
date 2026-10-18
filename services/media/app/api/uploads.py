"""Presigned multipart uploads (TRD §3.3, §7.3). The file's bytes never pass through this
service: the browser sends 8 MiB parts straight to the files host with the URLs given here."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from mms_common.auth import User, require_roles
from mms_common.errors import NotFound
from mms_common.ids import UUID7_PATTERN

from app.api.context import CtxDep
from app.api.schemas import MediaOut, PartUrl, UploadIn, UploadOut
from app.domain.media import part_count
from app.jobs import uploads
from app.repo import media as repo

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])

# Viewers never mutate (rule 5). The owner check decides whether this user may attach a file
# to this owner at all (a client to their own request, staff to a station).
Uploader = Annotated[User, Depends(require_roles("technician", "admin", "client"))]
MediaId = Annotated[str, Path(pattern=UUID7_PATTERN)]


def _out(state: uploads.UploadState, part_size: int) -> UploadOut:
    return UploadOut(
        media_id=state.doc["_id"], status=state.doc["status"], part_size=part_size,
        part_count=part_count(state.doc["size_bytes"], part_size),
        parts_done=state.parts_done,
        urls=[PartUrl(part_number=n, url=u) for n, u in sorted(state.urls.items())],
        expires_at=state.expires_at, resumed=state.resumed, media=MediaOut.of(state.doc),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_upload(body: UploadIn, user: Uploader, ctx: CtxDep) -> UploadOut:
    """Start an upload, or pick one up again. Idempotent by `media_id`; the same file chosen
    again after a reload continues the open upload, and the answer then names its `media_id`."""
    state = await uploads.create_upload(
        ctx.svc, user,
        uploads.NewUpload(body.media_id, body.owner_ref, body.kind, body.filename,
                          body.size_bytes, body.sha256),
        ctx.request_id,
    )
    return _out(state, ctx.svc.settings.part_size)


@router.post("/{media_id}/parts")
async def more_parts(media_id: MediaId, user: Uploader, ctx: CtxDep) -> UploadOut:
    """Fresh URLs for the parts still missing, and the parts already stored. Ask again when
    the URLs have expired (1 hour), or after a lost connection."""
    doc = await repo.get_uploaded_by(ctx.svc.db, user, media_id)
    if doc is None:
        raise NotFound()
    state = await uploads.part_urls(ctx.svc, doc)
    return _out(state, ctx.svc.settings.part_size)


@router.post("/{media_id}/complete")
async def complete(media_id: MediaId, user: Uploader, ctx: CtxDep) -> UploadOut:
    """Join the parts and queue the file for its checks (size, type, checksum, virus scan).
    Safe to repeat. The answer's `status` is `uploaded` until the checks finish."""
    state = await uploads.complete_upload(ctx.svc, user, media_id, ctx.actor(user))
    return _out(state, ctx.svc.settings.part_size)
