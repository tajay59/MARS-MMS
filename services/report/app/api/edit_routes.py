"""Editing a visit report draft and signing it (TRD 11.2, 11.3; PRD RPT-2, RPT-4, RPT-5;
W17-2 to W17-6).

Both need a connection (OFF-10) and both are draft-only: a final or superseded report is
immutable (rule 11). Attending staff and admins edit; the people who attended the visit sign (an
admin who did not attend does not). Each change and its event are one transaction (rule 2).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, status
from mms_common.auth import User, actor_for, require_roles
from mms_common.auth.deps import client_ip
from mms_common.errors import Conflict, Forbidden, NotFound
from mms_common.ids import UUID7_PATTERN, new_id
from mms_common.mongo import in_transaction
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api import presenters
from app.api.context import Ctx, CtxDep
from app.api.report_schemas import ContentPatch, ReportOut, SignIn
from app.domain import content as content_rules
from app.domain import signing
from app.events import publish
from app.events import signatures as sign_events
from app.repo import reports, signatures

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

Worker = Annotated[User, Depends(require_roles("technician", "admin"))]
ReportId = Annotated[str, Path(pattern=UUID7_PATTERN)]


class _Changed(Exception):  # noqa: N818 - control flow inside a transaction body, never escapes
    """The content moved on since the caller read it."""


async def _record(user: User, ctx: Ctx, report_id: str) -> ReportOut:
    s = ctx.svc
    doc = await reports.get(s.db, report_id)
    assert doc is not None  # noqa: S101 - it was just written
    return presenters.report_out(
        user, doc, await signatures.for_report(s.db, report_id), s.settings.attestation)


def _attending(user: User, doc: dict[str, Any] | None) -> dict[str, Any]:
    if doc is None:
        raise NotFound()
    if not user.is_admin and user.id not in doc["staff_ids"]:
        raise Forbidden("Only the people attending can do this", code="not_attending")
    return doc


def _draft(doc: dict[str, Any]) -> None:
    if doc["status"] != "draft":
        raise Conflict("Only a draft can be changed", code="not_a_draft")
    if doc["content"]["narrative"] is None or doc.get("content_hash") is None:
        raise Conflict("The draft is still being prepared", code="draft_not_ready")


async def _content_changed(user: User, ctx: Ctx, report_id: str) -> Conflict:
    """409 with the record as it is now, so the editor can show what changed."""
    current = await _record(user, ctx, report_id)
    return Conflict(
        "The report changed since you opened it", code="content_changed",
        content_version=current.content_version, current=current.model_dump(mode="json"),
    )


@router.patch("/{report_id}/content")
async def edit_content(
    report_id: ReportId, body: ContentPatch, user: Worker, ctx: CtxDep, request: Request
) -> ReportOut:
    """RPT-2: change the narrative or the photo choice of a draft. `content_version` is the one
    the editor read: another editor's save in between is 409 `content_changed`, unless this save
    is already in (a repeat after a lost answer), which changes nothing. A change that alters what
    prints clears the signatures (W17-3)."""
    s = ctx.svc
    _draft(_attending(user, await reports.get(s.db, report_id)))
    patch = body.model_dump(exclude_unset=True)
    actor = actor_for(request, user)

    async def save(session: AsyncClientSession) -> None:
        current = await reports.get(s.db, report_id, session)
        assert current is not None  # noqa: S101 - read above; reports are never deleted
        _draft(current)
        new = content_rules.edited(
            current["content"], narrative=patch.get("narrative"),
            media_selection=patch.get("media_selection"))
        new_hash = content_rules.content_hash(new)
        if new_hash == current["content_hash"]:
            return  # this edit is already in
        if body.content_version != current["content_version"]:
            raise _Changed
        if not await reports.set_content(
            s.db, report_id, expected_version=current["content_version"],
            narrative=new["narrative"], selection=new["media_selection"], content_hash=new_hash,
            now=s.clock.now(), session=session,
        ):
            raise _Changed
        await sign_events.clear(
            s.db, s.clock, current, reason="edit", by=user.id, actor=actor, session=session)

    try:
        await in_transaction(s.client, save)
    except _Changed:
        raise await _content_changed(user, ctx, report_id) from None
    return await _record(user, ctx, report_id)


@router.post("/{report_id}/sign", status_code=status.HTTP_201_CREATED)
async def sign(
    report_id: ReportId, body: SignIn, user: Worker, ctx: CtxDep, request: Request
) -> ReportOut:
    """RPT-4: a person who attended the visit signs the draft as it stands (`content_version`).
    The record keeps the drawing, the typed name, the attestation as shown, the time, address and
    browser, and the hash of the content (TRD 11.3). One valid signature each: signing again is
    409 `already_signed`. A change to the report clears every signature."""
    s = ctx.svc
    doc = await reports.get(s.db, report_id)
    if doc is None:
        raise NotFound()
    role = signing.role_of(doc, user.id)
    if role is None:
        raise Forbidden("Only the people who attended the visit can sign", code="not_attending")
    image, _, _ = signing.png_bytes(
        body.image, max_bytes=s.settings.signature_max_bytes,
        max_width=s.settings.signature_max_width, max_height=s.settings.signature_max_height)
    typed = signing.typed_name(body.typed_name)
    actor = actor_for(request, user)
    ip = client_ip(request)
    agent = (request.headers.get("User-Agent") or "")[:256] or None

    async def save(session: AsyncClientSession) -> None:
        current = await reports.get(s.db, report_id, session)
        assert current is not None  # noqa: S101 - read above; reports are never deleted
        _draft(current)
        if body.content_version != current["content_version"]:
            raise _Changed
        # Takes the draft at this version: an edit running at the same moment loses or wins
        # whole, and a signature never lands on content the signer did not read
        if not await reports.hold_version(
            s.db, report_id, current["content_version"], s.clock.now(), session
        ):
            raise _Changed
        if await signatures.valid_by(s.db, report_id, current["version"], user.id, session):
            raise Conflict("You have already signed this version", code="already_signed")
        await signatures.add(s.db, signing.new_signature(
            signature_id=new_id(), report=current, user_id=user.id, role=role, name=user.name,
            typed=typed, image=image, attestation=s.settings.attestation,
            signed_at=s.clock.now(), ip=ip, user_agent=agent), session)
        count = len(await signatures.valid(s.db, report_id, current["version"], session))
        await publish.signed(
            s.db, s.clock, current, signer_id=user.id, role=role, valid_signatures=count,
            actor=actor, session=session)

    try:
        await in_transaction(s.client, save)
    except _Changed:
        raise await _content_changed(user, ctx, report_id) from None
    return await _record(user, ctx, report_id)
