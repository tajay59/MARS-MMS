"""Internal-network routes. Nginx never routes `/internal/` (TRD §2.1)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from mms_common.auth import ServicePrincipal, require_service
from mms_common.errors import Conflict, NotFound
from mms_common.ids import UUID7_PATTERN

from app.api.context import CtxDep
from app.api.schemas import MediaInfo, UrlIn, UrlOut
from app.domain import media as rules
from app.domain.media import Status
from app.repo import media as repo

router = APIRouter(tags=["internal"])

Owner = Annotated[ServicePrincipal, Depends(require_service("operations"))]
MediaId = Annotated[str, Path(pattern=UUID7_PATTERN)]


@router.get("/internal/media/{media_id}")
async def media_info(media_id: MediaId, svc: Owner, ctx: CtxDep) -> MediaInfo:
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
