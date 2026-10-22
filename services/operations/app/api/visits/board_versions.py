"""Configuration versions made from a board's Config elements (CFG-4; W11-24, W11-37).

The end of a visit makes one for each Config element whose After files are not yet a version;
after the end, the sheet's "Save as version" makes the next one when they change. Files are asked
about first (a network call, before the transaction): a version holds only files that passed their
checks, so one still being checked makes the caller wait (409 `config_files_not_ready`). A version
never changes (CFG-2), and a deleted element keeps the versions it made.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from mms_common.auth import User
from mms_common.errors import Conflict
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx
from app.domain.stations.documents import FileFacts
from app.domain.visits import elements as rules
from app.events.publish import Emitter
from app.repo.requests import comments as file_repo
from app.repo.stations import documents as config_repo
from app.repo.stations import stations as station_repo
from app.repo.stations.common import stamp
from app.repo.visits import elements as element_repo

Checked = list[tuple[Mapping[str, Any], FileFacts]]


async def checked_files(ctx: Ctx, element: Mapping[str, Any]) -> Checked:
    """The element's version files with what media says of each; refuses while any is not ready."""
    files = rules.config_files(element)
    found = await asyncio.gather(
        *(file_repo.file_facts(ctx.media, e["media_id"], ctx.request_id) for e in files))
    waiting = [e["filename"] for e, f in zip(files, found, strict=True)
               if f is None or f.status != "ready"]
    if waiting:
        names = ", ".join(waiting)
        raise Conflict(
            f"Wait a moment: {names} on {element['title']} {'is' if len(waiting) == 1 else 'are'} "
            "still being checked", code="config_files_not_ready", files=waiting,
            element_id=element["_id"])
    return [(e, f) for e, f in zip(files, found, strict=True) if f is not None]


async def make_version(
    ctx: Ctx, user: User, visit: Mapping[str, Any], element: Mapping[str, Any], checked: Checked,
    version_id: str, s: AsyncClientSession, emitter: Emitter,
) -> dict[str, Any]:
    """Write the station's next version from the element's After files, and note it on the
    element. Returns the element as it is now."""
    now = ctx.clock.now()
    station = await station_repo.require(ctx.db, element["station_id"], None, s)
    number = await config_repo.next_version(ctx.db, station["_id"], s)
    doc = {**stamp({
        "_id": version_id, "station_id": station["_id"],
        "files": [
            {"media_id": entry["media_id"], "filename": facts.filename,
             "sha256": facts.checksum_sha256, "size_bytes": facts.size_bytes}
            for entry, facts in checked
        ],
        "notes": element["title"], "visit_id": visit["_id"], "created_by_name": user.name,
        "from_board": True, "element_id": element["_id"],
    }, now, user.id), "version": number}
    await config_repo.insert_version(ctx.db, doc, s)
    await emitter.config_version(doc, station, s)
    made = [*element.get("config_versions", []),
            {"id": version_id, "version": number,
             "media_ids": [entry["media_id"] for entry, _ in checked]}]
    updated = await element_repo.set_fields(
        ctx.db, element["_id"], {"config_versions": made,
                                 "config_version_ids": [m["id"] for m in made]},
        now=now, by=user.id, session=s)
    return updated if updated is not None else dict(element)
