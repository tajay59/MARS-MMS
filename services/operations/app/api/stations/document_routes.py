"""Documents (TRD §3.2; PRD DOC-1 to DOC-4). Model documents (datasheets, manuals) show on
every station using the model; station documents belong to one station.

A document is created as soon as its file is whole and is downloadable once media has
checked it. Staff-only is the default; making a document client-visible asks media to show
its file to the owner organization in the same transaction (ADR-19).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, NotFound, ValidationFailed
from mms_common.ids import UUID7_PATTERN
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import CtxDep
from app.api.stations.doc_schemas import (
    DocumentIn,
    DocumentOut,
    DocumentPage,
    DocumentPatch,
    DownloadOut,
    ModelDocuments,
    StationDocuments,
)
from app.domain.stations import documents as rules
from app.domain.stations.documents import DocStatus, FileFacts, Scope
from app.events.publish import ev
from app.repo.stations import documents as repo
from app.repo.stations import models, units
from app.repo.stations import stations as station_repo
from app.repo.stations.common import stamp

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
station_router = APIRouter(prefix="/api/v1/stations", tags=["documents"])

Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client what they may
Writer = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


class FileInUse(Conflict):
    code, title = "file_in_use", "That file is already attached to another document"


class IdReused(Conflict):
    code, title = "id_reused", "That ID was used for a different document"


async def file_facts(ctx: Any, media_id: str) -> FileFacts | None:
    """What media knows about a file, as the rules want it."""
    info = await ctx.media.info(media_id, ctx.request_id)
    if info is None:
        return None
    return FileFacts(
        owner_ref=info.owner_ref, kind=info.kind, status=info.status,
        uploaded_by=info.uploaded_by, filename=info.filename, size_bytes=info.size_bytes,
        checksum_sha256=info.checksum_sha256, scan_status=info.scan_status,
    )


@router.get("")
async def list_documents(
    viewer: Reader,
    ctx: CtxDep,
    scope: Annotated[rules.Scope | None, Query()] = None,
    scope_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    doc_type: Annotated[str | None, Query(max_length=30)] = None,
    current: Annotated[bool, Query(description="Only the newest version of each")] = True,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> DocumentPage:
    """DOC-1, DOC-2. A client sees the current, client-visible, clean documents of their own
    stations and of the models installed there. Staff see every version when `current=false`."""
    found = await repo.search(
        ctx.db, viewer, scope=scope.value if scope else None, scope_id=scope_id,
        doc_type=doc_type, current_only=current or viewer.is_client, after=after,
        limit=limit + 1,
    )
    more = len(found) > limit
    found = found[:limit]
    return DocumentPage(items=[DocumentOut.of(d, viewer) for d in found],
                        next_after=found[-1]["_id"] if more else None)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentIn, response: Response, user: Writer, ctx: CtxDep
) -> DocumentOut:
    """DOC-3. Idempotent by `id`: a retry returns the document it made. `supersedes_id` makes
    this a new version; the earlier one stays downloadable by staff."""
    scope = Scope(body.scope)
    existing = await repo.get(ctx.db, body.id)
    if existing is not None:
        if existing["created_by"] != user.id or existing["media_id"] != body.media_id:
            raise IdReused()
        response.status_code = status.HTTP_200_OK
        return DocumentOut.of(existing, user)

    doc_type = rules.check_doc_type(scope, body.doc_type)
    org_id: str | None = None
    if scope is Scope.STATION:
        station = await station_repo.get(ctx.db, body.scope_id)
        if station is None:
            raise ValidationFailed("That station wasn't found", code="unknown_target",
                                   field="scope_id")
        org_id = station["owner_org_id"]
    elif await models.get(ctx.db, body.scope_id) is None:
        raise ValidationFailed("That sensor model wasn't found", code="unknown_target",
                               field="scope_id")

    facts = rules.check_file(
        await file_facts(ctx, body.media_id), owner=rules.owner_ref(scope, body.scope_id),
        kinds=rules.DOCUMENT_KINDS, user_id=user.id,
    )
    if await repo.by_media(ctx.db, body.media_id) is not None:
        raise FileInUse()
    old: dict[str, Any] | None = None
    if body.supersedes_id:
        old = await repo.get(ctx.db, body.supersedes_id)
        if (old is None or old["scope"] != scope.value or old["scope_id"] != body.scope_id
                or not old["is_current"]):
            raise ValidationFailed(
                f"Choose the current version of a {scope.value} document",
                code="bad_supersedes", field="supersedes_id",
            )

    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        # Media's verdict may already be in, or arrive while this commits: see touch_outcome.
        outcome = (await repo.touch_outcome(ctx.db, body.media_id, now, s)).get("outcome") or {}
        state = rules.status_for(facts.status)
        scan = facts.scan_status if state is DocStatus.AVAILABLE else None
        if outcome.get("kind") == "processed":
            state, scan = DocStatus.AVAILABLE, outcome.get("scan_status")
        elif outcome.get("kind") == "failed":
            state = DocStatus.FAILED
        doc = stamp({
            "_id": body.id, "scope": scope.value, "scope_id": body.scope_id, "org_id": org_id,
            "doc_type": doc_type, "title": body.title, "version_label": body.version_label,
            "language": body.language, "description": body.description,
            "client_visible": body.client_visible, "media_id": body.media_id,
            "filename": facts.filename, "size_bytes": facts.size_bytes,
            "supersedes_id": body.supersedes_id, "is_current": True, "status": state.value,
            "scan_status": scan, "error": outcome.get("reason"),
            "created_by_name": user.name,
        }, now, user.id)
        await repo.insert(ctx.db, doc, s)
        if old is not None:
            replaced = await repo.update(ctx.db, old["_id"], {"is_current": False}, now=now,
                                         by=user.id, expected_version=old["version"], session=s)
            await emitter.document(ev.DocumentUpdated, replaced, s, before=old,
                                   changed_fields=["is_current"])
            if scope is Scope.STATION and replaced["client_visible"]:
                await emitter.visibility(replaced, "staff", s)  # earlier versions go back
        await emitter.document(ev.DocumentUploaded, doc, s, version_label=body.version_label,
                               supersedes_id=body.supersedes_id)
        if scope is Scope.STATION and body.client_visible:
            await emitter.visibility(doc, "org", s)
        return doc

    try:
        doc = await ctx.tx(save)
    except DuplicateKeyError as exc:
        keys = (exc.details or {}).get("keyPattern") or {}
        raise (FileInUse() if "media_id" in keys else IdReused()) from exc
    return DocumentOut.of(doc, user)


@router.get("/{id}")
async def get_document(id: IdPath, viewer: Reader, ctx: CtxDep) -> DocumentOut:
    doc = await repo.get(ctx.db, id, viewer)
    if doc is None:
        raise NotFound()
    return DocumentOut.of(doc, viewer)


@router.patch("/{id}")
async def patch_document(
    id: IdPath, body: DocumentPatch, user: Writer, ctx: CtxDep
) -> DocumentOut:
    """Change the details of a document, or who may see it (DOC-4). The file itself never
    changes: upload a new version instead."""
    current = await repo.get(ctx.db, id)
    if current is None:
        raise NotFound()
    scope = Scope(current["scope"])
    changes: dict[str, Any] = {}
    for field in body.model_fields_set - {"version"}:
        value = getattr(body, field)
        if value is None and field in ("title", "doc_type", "client_visible"):
            raise ValidationFailed(f"{field} can't be empty", code="required", field=field)
        if field == "doc_type":
            value = rules.check_doc_type(scope, value)
        if value != current.get(field):
            changes[field] = value
    if not changes:
        if body.version != current["version"]:
            raise Conflict("The document changed. Reload and try again", reason="version_conflict")
        return DocumentOut.of(current, user)
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await repo.update(ctx.db, id, changes, now=now, by=user.id,
                                    expected_version=body.version, session=s)
        await emitter.document(ev.DocumentUpdated, updated, s, before=current,
                               changed_fields=sorted(changes))
        if "client_visible" in changes and scope is Scope.STATION:
            await emitter.visibility(updated, "org" if updated["client_visible"] else "staff", s)
        return updated

    return DocumentOut.of(await ctx.tx(save), user)


@router.get("/{id}/download")
async def download_document(
    id: IdPath, viewer: Reader, ctx: CtxDep,
    inline: Annotated[bool, Query(description="Open PDFs and images in the browser")] = True,
) -> DownloadOut:
    """Check access, then ask media for a ten-minute link (model documents have no
    organization in media, so this is the only way a client reaches them: BSD B4)."""
    doc = await repo.get(ctx.db, id, viewer)
    if doc is None:
        raise NotFound()
    if doc["status"] != DocStatus.AVAILABLE.value:
        raise Conflict("The file is still being checked" if doc["status"] == "pending"
                       else "The file didn't pass its checks. Upload it again",
                       reason="not_ready" if doc["status"] == "pending" else "file_failed")
    link = await ctx.media.link(doc["media_id"], inline=inline, request_id=ctx.request_id)
    return DownloadOut(url=link.url, expires_at=link.expires_at, filename=doc["filename"])


@station_router.get("/{id}/documents")
async def station_documents(id: IdPath, viewer: Reader, ctx: CtxDep) -> StationDocuments:
    """The station page's Documents tab: its own documents and its sensors' manuals (DOC-1,
    DOC-2). Only the current version of each."""
    await station_repo.require(ctx.db, id, viewer)
    installed = await units.installed_at(ctx.db, id)
    model_ids = sorted({u["model_id"] for u in installed})
    own, from_models = await repo.for_station(ctx.db, viewer, id, model_ids)
    names = await models.by_ids(ctx.db, model_ids)
    groups: list[ModelDocuments] = []
    for model_id in model_ids:
        found = [d for d in from_models if d["scope_id"] == model_id]
        model = names.get(model_id)
        if found and model:
            groups.append(ModelDocuments(
                model_id=model_id, manufacturer=model["manufacturer"], model=model["model"],
                documents=[DocumentOut.of(d, viewer) for d in found],
            ))
    return StationDocuments(station=[DocumentOut.of(d, viewer) for d in own], models=groups)
