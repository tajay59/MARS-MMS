"""Configuration versions (TRD §3.2; PRD CFG-1 to CFG-3). Staff only.

A version is a numbered set of files with change notes. It is written once and never changed
or deleted through the app (CFG-2), so it takes only files that have already passed media's
checks. Clients never see configuration versions (rule 6).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mms_common.auth import User, require_roles, require_staff
from mms_common.errors import Conflict, NotFound, ValidationFailed
from mms_common.ids import UUID7_PATTERN
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import CtxDep
from app.api.stations.doc_schemas import ConfigDiff, ConfigVersionIn, ConfigVersionOut
from app.api.stations.document_routes import IdReused, file_facts
from app.domain.stations import documents as rules
from app.repo.stations import documents as repo
from app.repo.stations import stations as station_repo
from app.repo.stations.common import stamp

router = APIRouter(prefix="/api/v1/stations", tags=["configuration"])

Staff = Annotated[User, Depends(require_staff())]
Writer = Annotated[User, Depends(require_roles("technician", "admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
Version = Annotated[int, Path(ge=1, le=1_000_000)]


class FileInUse(Conflict):
    code, title = "file_in_use", "A file is already part of a configuration version"


@router.get("/{id}/config-versions")
async def list_config_versions(id: IdPath, staff: Staff, ctx: CtxDep) -> list[ConfigVersionOut]:
    """CFG-3: newest first."""
    await station_repo.require(ctx.db, id, staff)
    return [ConfigVersionOut.of(d) for d in await repo.list_versions(ctx.db, id)]


@router.post("/{id}/config-versions", status_code=status.HTTP_201_CREATED)
async def create_config_version(
    id: IdPath, body: ConfigVersionIn, response: Response, user: Writer, ctx: CtxDep
) -> ConfigVersionOut:
    """CFG-1, CFG-2. Idempotent by `id`. Every file must be one this person uploaded for this
    station and that has passed its checks; if one is still being checked the answer is a
    409 `file_not_ready`, and trying again a moment later works."""
    station = await station_repo.require(ctx.db, id, user)
    existing = await repo.version_by_id(ctx.db, body.id)
    if existing is not None:
        if existing["station_id"] != id or existing["created_by"] != user.id or [
            f["media_id"] for f in existing["files"]
        ] != [f.media_id for f in body.files]:
            raise IdReused()
        response.status_code = status.HTTP_200_OK
        return ConfigVersionOut.of(existing)

    ids = [f.media_id for f in body.files]
    if len(set(ids)) != len(ids):
        raise ValidationFailed("A file is listed twice", code="duplicate_file", field="files")
    found = await asyncio.gather(*(file_facts(ctx, m) for m in ids))
    owner = rules.config_owner_ref(id)
    checked = [
        rules.check_file(f, owner=owner, kinds=rules.CONFIG_KINDS, user_id=user.id,
                         ready_only=True)
        for f in found
    ]
    rules.check_unique_names(checked)
    for media_id in ids:
        if await repo.version_with_file(ctx.db, media_id) is not None:
            raise FileInUse()

    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        number = await repo.next_version(ctx.db, id, s)
        # `version` is the number here (TRD §5.2), not the record's concurrency counter:
        # a configuration version is written once and never changes (CFG-2).
        doc = {**stamp({
            "_id": body.id, "station_id": id,
            "files": [
                {"media_id": m, "filename": f.filename, "sha256": f.checksum_sha256,
                 "size_bytes": f.size_bytes}
                for m, f in zip(ids, checked, strict=True)
            ],
            "notes": body.notes, "visit_id": body.visit_id, "created_by_name": user.name,
        }, now, user.id), "version": number}
        await repo.insert_version(ctx.db, doc, s)
        await emitter.config_version(doc, station, s)
        return doc

    try:
        doc = await ctx.tx(save)
    except DuplicateKeyError as exc:
        keys = (exc.details or {}).get("keyPattern") or {}
        raise (FileInUse() if "files.media_id" in keys else IdReused()) from exc
    return ConfigVersionOut.of(doc)


@router.get("/{id}/config-versions/{version}")
async def get_config_version(
    id: IdPath, version: Version, staff: Staff, ctx: CtxDep
) -> ConfigVersionOut:
    await station_repo.require(ctx.db, id, staff)
    doc = await repo.get_version(ctx.db, id, version)
    if doc is None:
        raise NotFound()
    return ConfigVersionOut.of(doc)


@router.get("/{id}/config-versions/{version}/diff")
async def diff_config_versions(
    id: IdPath, version: Version, staff: Staff, ctx: CtxDep,
    against: Annotated[int | None, Query(ge=1, le=1_000_000)] = None,
) -> ConfigDiff:
    """CFG-3: files added, removed or changed since `against` (default: the version before).
    Version 1 compared with nothing lists every file as added."""
    await station_repo.require(ctx.db, id, staff)
    new = await repo.get_version(ctx.db, id, version)
    if new is None:
        raise NotFound()
    base = against if against is not None else version - 1
    old: dict[str, Any] | None = None
    if base >= 1:
        old = await repo.get_version(ctx.db, id, base)
        if old is None:
            raise NotFound()
    d = rules.diff_files(old["files"] if old else [], new["files"])
    return ConfigDiff(
        version=version, against=base if old else None, added=d.added, removed=d.removed,
        changed=d.changed, unchanged=d.unchanged,
    )
