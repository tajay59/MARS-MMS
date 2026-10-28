"""A client's own reports on a request (PRD CRP-1 to CRP-5; TRD 3.2; AFD J9; decisions W18-9,
W18-10).

A client uploads one PDF or fills in an online form. A draft is private to its author and can be
changed; submitting it makes it read-only for good (CRP-4), shows its files to the organization
(ADR-19) and tells the report service to draw a form's PDF. Staff read submitted reports. The
filter lives in `repo/client_reports.py`; a report outside the caller's scope is 404 (rule 4).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, Forbidden, ValidationFailed
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.client_reports.schemas import (
    ClientReportIn,
    ClientReportOut,
    ClientReportPage,
    ClientReportPatch,
)
from app.api.context import Ctx, CtxDep
from app.api.requests.attach import FileInUse
from app.api.requests.comment_routes import _download
from app.api.stations.doc_schemas import DownloadOut
from app.domain import client_reports as rules
from app.repo import client_reports as repo
from app.repo.requests import comments as comment_repo
from app.repo.requests import requests as request_repo
from app.repo.stations.common import stamp

router = APIRouter(prefix="/api/v1/client-reports", tags=["client-reports"])

Reader = Annotated[User, Depends(require_roles())]  # staff read; a client their own organization
Client = Annotated[User, Depends(require_roles("client"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
MediaPath = Annotated[str, Path(pattern=UUID7_PATTERN)]


def _blank_form() -> dict[str, Any]:
    return {"summary": "", "observations": [], "data_quality_notes": "", "images": []}


async def _upload(
    ctx: Ctx, user: User, report_id: str, media_id: str, kind: rules.Kind, field: str
) -> dict[str, Any]:
    """A clean file this person uploaded for this report, not used elsewhere."""
    facts = rules.check_upload(
        await comment_repo.file_facts(ctx.media, media_id, ctx.request_id),
        report_id=report_id, user_id=user.id, kind=kind, field=field,
    )
    if await repo.media_in_use(ctx.db, media_id, report_id):
        raise FileInUse()
    return rules.attachment(facts, media_id)


@router.get("")
async def list_client_reports(
    viewer: Reader, ctx: CtxDep,
    request_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    station_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ClientReportPage:
    """CRP-5: newest first. A client gets their organization's submitted reports and their own
    drafts; staff get submitted reports."""
    found = await repo.search(ctx.db, viewer, request_id=request_id, station_id=station_id,
                              limit=limit)
    return ClientReportPage(items=[ClientReportOut.of(d, viewer) for d in found])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_client_report(
    body: ClientReportIn, response: Response, user: Client, ctx: CtxDep
) -> ClientReportOut:
    """CRP-1, CRP-2: start a draft on a request of the client's organization. Idempotent by
    `id`: sending it again returns the draft already made (200)."""
    request = await request_repo.require(ctx.db, body.request_id, user)
    report_id = body.id or new_id()
    existing = await repo.get(ctx.db, report_id, None)
    if existing is not None:
        if existing["created_by"] != user.id:
            raise Conflict("That ID is already used", code="id_taken")
        response.status_code = status.HTTP_200_OK
        return ClientReportOut.of(existing, user)
    rules.check_request(request["status"])
    now = ctx.clock.now()
    stations = rules.check_stations(body.station_ids or request["station_ids"],
                                    request["station_ids"])
    doc = stamp({
        "_id": report_id, "request_id": request["_id"], "request_ref": request["ref"],
        "org_id": request["org_id"], "kind": body.kind, "status": rules.State.DRAFT.value,
        "title": rules.clean_title(body.title, required=False),
        "report_date": rules.check_date(body.report_date or now.date()).isoformat(),
        "station_ids": stations, "file": None, "form": _blank_form(),
        "render": rules.Render.NONE.value, "report_id": None, "attempt": 0,
        "submitted_by": None, "submitted_by_name": None, "submitted_at": None,
    }, now, user.id)

    async def save(s: AsyncClientSession) -> None:
        await repo.insert(ctx.db, doc, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        # The same `id` arrived twice at once: the other one won. Hand back what it made.
        won = await repo.get(ctx.db, report_id, None)
        if won is None or won["created_by"] != user.id:
            raise Conflict("That ID is already used", code="id_taken") from None
        response.status_code = status.HTTP_200_OK
        return ClientReportOut.of(won, user)
    return ClientReportOut.of(doc, user)


@router.get("/{id}")
async def get_client_report(id: IdPath, viewer: Reader, ctx: CtxDep) -> ClientReportOut:
    return ClientReportOut.of(await repo.require(ctx.db, id, viewer), viewer)


@router.patch("/{id}")
async def update_client_report(
    id: IdPath, body: ClientReportPatch, user: Client, ctx: CtxDep
) -> ClientReportOut:
    """CRP-2: change a draft. A submitted report can't be changed (CRP-4): 409 `not_a_draft`.
    A draft is private, so it is not an event."""
    current = await repo.require(ctx.db, id, user)
    if not rules.can_edit(current, user.id):
        raise Conflict("A submitted report can't be changed. Add a new one instead",
                       code="not_a_draft")
    request = await request_repo.require(ctx.db, current["request_id"], user)
    rules.check_request(request["status"])
    pdf = current["kind"] == rules.Kind.PDF.value
    sent = body.model_fields_set
    if pdf and sent & {"summary", "observations", "data_quality_notes", "image_ids"}:
        raise ValidationFailed("A PDF report has no form", code="wrong_kind", field="summary")
    if not pdf and "media_id" in sent:
        raise ValidationFailed("A form report holds pictures, not a PDF", code="wrong_kind",
                               field="media_id")

    changes: dict[str, Any] = {}
    form = dict(current["form"])
    if body.title is not None:
        changes["title"] = rules.clean_title(body.title, required=False)
    if body.report_date is not None:
        changes["report_date"] = rules.check_date(body.report_date).isoformat()
    stations = list(current["station_ids"])
    if body.station_ids is not None:
        stations = rules.check_stations(body.station_ids, request["station_ids"])
        changes["station_ids"] = stations
        # A note about a station the report no longer covers goes with it
        form["observations"] = [o for o in form["observations"] if o["station_id"] in stations]
    if "media_id" in sent:
        changes["file"] = (
            await _upload(ctx, user, id, body.media_id, rules.Kind.PDF, "media_id")
            if body.media_id else None
        )
    if body.summary is not None:
        form["summary"] = rules.clean_text(body.summary, limit=rules.MAX_SUMMARY, field="summary")
    if body.observations is not None:
        form["observations"] = rules.check_observations(
            [o.model_dump() for o in body.observations], stations)
    if body.data_quality_notes is not None:
        form["data_quality_notes"] = rules.clean_text(
            body.data_quality_notes, limit=rules.MAX_NOTES, field="data_quality_notes")
    if body.image_ids is not None:
        ids = rules.check_image_ids(body.image_ids)
        kept = {i["media_id"]: i for i in form["images"]}
        form["images"] = [
            kept.get(m) or await _upload(ctx, user, id, m, rules.Kind.FORM, "image_ids")
            for m in ids
        ]
    if form != current["form"]:
        changes["form"] = form
    changes = {k: v for k, v in changes.items() if current.get(k) != v}
    if not changes:
        if body.version != current["version"]:
            raise Conflict("The report changed. Reload and try again", code="version_conflict")
        return ClientReportOut.of(current, user)
    now = ctx.clock.now()

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        return await repo.update(ctx.db, id, changes, now=now, by=user.id,
                                 expected_version=body.version, session=s)

    return ClientReportOut.of(await ctx.tx(save), user)


@router.post("/{id}/submit")
async def submit_client_report(id: IdPath, user: Client, ctx: CtxDep) -> ClientReportOut:
    """CRP-3, CRP-4: send the report. From now on nobody can change it. Safe to send twice: a
    report already sent is returned as it is. A form report whose PDF could not be drawn is
    sent for drawing once more (Try again), and nothing else about it changes."""
    current = await repo.require(ctx.db, id, user)
    if current["created_by"] != user.id:
        raise Forbidden()
    if current["status"] == rules.State.SUBMITTED.value and not rules.can_submit_again(current):
        return ClientReportOut.of(current, user)
    request = await request_repo.require(ctx.db, current["request_id"], user)
    again = current["status"] == rules.State.SUBMITTED.value
    if not again:
        rules.check_request(request["status"])
        rules.ready_to_submit(current)
        # The files are checked again now: what is attached must still be clean and this
        # person's (a draft can sit for days)
        if current["kind"] == rules.Kind.PDF.value:
            await _upload(ctx, user, id, current["file"]["media_id"], rules.Kind.PDF, "media_id")
        else:
            for image in current["form"]["images"]:
                await _upload(ctx, user, id, image["media_id"], rules.Kind.FORM, "image_ids")
    now = ctx.clock.now()
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        fresh = await repo.require(ctx.db, id, None, s)
        if fresh["version"] != current["version"]:
            # Another submit got here first (two taps, two tabs): hand back what it made
            if fresh["status"] == rules.State.SUBMITTED.value:
                return fresh
            raise Conflict("The report changed. Reload and try again", code="version_conflict")
        changes: dict[str, Any] = {"render": rules.render_after_submit(fresh["kind"]).value,
                                   "attempt": int(fresh["attempt"]) + 1}
        if not again:
            changes.update(status=rules.State.SUBMITTED.value, submitted_by=user.id,
                           submitted_by_name=user.name, submitted_at=now)
        updated = await repo.update(ctx.db, id, changes, now=now, by=user.id,
                                    expected_version=fresh["version"], session=s)
        await emitter.client_report(updated, request, s, before=fresh)
        files = rules.media_ids(updated)
        if files and not again:
            await emitter.attachments_visibility("client_report", updated, request, files, "org",
                                                 s)
        return updated

    return ClientReportOut.of(await ctx.tx(save), user)


@router.get("/{id}/download")
async def download_client_report(id: IdPath, viewer: Reader, ctx: CtxDep) -> DownloadOut:
    """A ten-minute link to a PDF report's file. A form report's PDF is the report service's:
    ask `/api/v1/reports/{report_id}/download`."""
    doc = await repo.require(ctx.db, id, viewer)
    if doc["kind"] != rules.Kind.PDF.value or not doc.get("file"):
        raise Conflict("This report's PDF is served from the reports list",
                       code="use_report_download")
    return await _download(ctx, [doc["file"]], doc["file"]["media_id"])


@router.get("/{id}/attachments/{media_id}/download")
async def download_client_report_file(
    id: IdPath, media_id: MediaPath, viewer: Reader, ctx: CtxDep
) -> DownloadOut:
    """A picture attached to a form report (or the report's PDF), for the page to show."""
    doc = await repo.require(ctx.db, id, viewer)
    entries = [*doc["form"]["images"], *([doc["file"]] if doc.get("file") else [])]
    return await _download(ctx, entries, media_id)

