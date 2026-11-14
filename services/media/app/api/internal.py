"""Internal-network routes. Nginx never routes `/internal/` (TRD §2.1)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response
from mms_common.auth import ServicePrincipal, require_service
from mms_common.errors import Conflict, NotFound
from mms_common.ids import UUID7_PATTERN

from app.api.context import CtxDep
from app.api.schemas import MediaInfo, UrlIn, UrlOut
from app.domain import derive
from app.domain import media as rules
from app.domain.media import Status
from app.repo import media as repo

router = APIRouter(tags=["internal"])

Owner = Annotated[ServicePrincipal, Depends(require_service("operations"))]
# The report service reads a file's record and its display copy for a visit report (W16-7)
Reader = Annotated[ServicePrincipal, Depends(require_service("operations", "report"))]
MediaId = Annotated[str, Path(pattern=UUID7_PATTERN)]


@router.get("/internal/media/{media_id}")
async def media_info(media_id: MediaId, svc: Reader, ctx: CtxDep) -> MediaInfo:
    """Operations checks a file before it attaches it to a document: who uploaded it, for
    which owner, and where it stands."""
    doc = await repo.get(ctx.svc.db, media_id)
    if doc is None or doc["status"] == Status.DELETED.value:
        raise NotFound()
    return MediaInfo(
        id=doc["_id"], owner_ref=doc["owner_ref"], kind=doc["kind"], filename=doc["filename"],
        size_bytes=doc["size_bytes"], status=doc["status"], uploaded_by=doc["uploaded_by"],
        org_id=doc.get("org_id"), checksum_sha256=doc["checksum_sha256"],
        scan_status=doc.get("scan_status"),
    )


@router.post("/internal/media/{media_id}/url")
async def media_url(media_id: MediaId, body: UrlIn, svc: Owner, ctx: CtxDep) -> UrlOut:
    """A download link for a caller that has done its own access check (model documents,
    TRD §3.2). Only a file that passed its checks gets one."""
    s = ctx.svc
    doc = await repo.get(s.db, media_id)
    if doc is None or doc["status"] == Status.DELETED.value:
        raise NotFound()
    if doc["status"] != Status.READY.value:
        raise Conflict("The file isn't ready", reason="not_ready")
    filename = str(doc["filename"])
    url = s.storage.get_url(
        s.bucket(doc["kind"]), doc["original_key"], s.settings.get_url_ttl_s,
        content_type=rules.content_type(filename),
        disposition=rules.disposition(filename, inline=body.inline),
    )
    return UrlOut(url=url, expires_at=s.clock.now() + timedelta(seconds=s.settings.get_url_ttl_s))


@router.get("/internal/media/{media_id}/rendition")
async def media_rendition(
    media_id: MediaId, svc: Reader, ctx: CtxDep,
    variant: Annotated[str, Query(pattern="^(view|thumbnail)$")] = "view",
) -> Response:
    """A processed file's picture as bytes, for a visit report's PDF (TRD 11.1, W16-7). `view`:
    the display copy of a photo (up to 2048 px on the long side; the report service shrinks it
    for the page). `thumbnail`: the small WebP of a photo or a video's poster frame. The report
    service has no rights on media's buckets, and the files host is not reachable from its
    network by its public name."""
    s = ctx.svc
    doc = await repo.get(s.db, media_id)
    if doc is None or doc["status"] == Status.DELETED.value:
        raise NotFound()
    if doc["status"] != Status.READY.value:
        raise Conflict("The file isn't ready", reason="not_ready")
    if variant == "thumbnail":
        key, content_type = doc.get("thumbnail_key"), "image/webp"
    else:
        key, content_type = doc.get("processed_key"), derive.view_type("image")
        if doc["kind"] != "image":
            key = None
    if not key:
        raise NotFound()
    data = b"".join([chunk async for chunk in s.storage.read(s.settings.bucket_media, str(key))])
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "no-store"})
