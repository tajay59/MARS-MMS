"""Users and organizations (TRD §3.1; AUTH-3, AUTH-6, AUTH-11, ORG-1, ORG-4; AFD J1)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from mms_common.auth import User, require_roles, revocation
from mms_common.errors import Conflict, ValidationFailed
from mms_common.ids import UUID7_PATTERN, new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import Ctx, CtxDep
from app.api.schemas import (
    ApproveIn,
    InviteIn,
    OrgIn,
    OrgOut,
    OrgPage,
    OrgPatch,
    RejectIn,
    UserOut,
    UserPage,
    UserPatch,
)
from app.domain import users as rules
from app.events.publish import Emitter, ev
from app.repo import links, organizations, sessions
from app.repo import users as users_repo
from app.repo.links import Kind

users = APIRouter(prefix="/api/v1/users", tags=["users"])
orgs = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])

Admin = Annotated[User, Depends(require_roles("admin"))]
Reader = Annotated[User, Depends(require_roles())]  # staff read all; a client reads own org
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
Limit = Annotated[int, Query(ge=1, le=200)]


class EmailTaken(Conflict):
    code, title = "email_taken", "An account with this email already exists"


class OrgNameTaken(Conflict):
    code, title = "org_name_taken", "An organization with this name already exists"


class OrgExternalIdTaken(Conflict):
    code, title = "org_external_id_taken", "Another organization has this external ID"


def _org_conflict(exc: DuplicateKeyError) -> Conflict:
    """Which unique field clashed: the name or the external ID."""
    pattern = (exc.details or {}).get("keyPattern") or {}
    return OrgExternalIdTaken() if "external_id" in pattern else OrgNameTaken()


# --- Users ------------------------------------------------------------------------------------


@users.get("")
async def list_users(
    admin: Admin,
    ctx: CtxDep,
    status_: Annotated[rules.Status | None, Query(alias="status")] = None,
    role: Annotated[str | None, Query(pattern="^(client|technician|admin|viewer)$")] = None,
    org_id: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Limit = 50,
) -> UserPage:
    found = await users_repo.search(
        ctx.db, status=status_.value if status_ else None, role=role, org_id=org_id, q=q,
        after=after, limit=limit + 1,
    )
    more = len(found) > limit
    found = found[:limit]
    return UserPage(
        items=[UserOut.of(d) for d in found], next_after=found[-1]["_id"] if more else None
    )


@users.post("", status_code=status.HTTP_201_CREATED)
async def invite_user(body: InviteIn, admin: Admin, ctx: CtxDep) -> UserOut:
    """Staff accounts are always created this way; clients can be invited too (AUTH-6)."""
    email = rules.normalize_email(body.email)
    if not rules.valid_email(email):
        raise ValidationFailed("Enter a valid email", code="invalid_email")
    roles: list[str] = sorted(set(body.roles))
    rules.check_roles(roles, body.org_id)
    if body.org_id:
        org = await organizations.get(ctx.db, body.org_id)
        if org is None or org["status"] != rules.OrgStatus.ACTIVE:
            raise ValidationFailed("Choose an active organization", code="org_inactive")
    if await users_repo.find_by_email(ctx.db, email) is not None:
        raise EmailTaken()
    now = ctx.clock.now()
    doc: dict[str, Any] = {
        "_id": new_id(), "email": email, "password_hash": None, "name": body.name,
        "phone": body.phone, "time_zone": None, "theme": rules.Theme.SYSTEM.value,
        "roles": roles, "org_id": body.org_id, "proposed_org_name": None,
        "status": rules.Status.INVITED.value, "rejection_reason": None, "last_login_at": None,
        "created_at": now, "updated_at": now, "created_by": admin.id, "updated_by": admin.id,
        "version": 1,
    }
    expires_at = now + timedelta(days=ctx.settings.invitation_ttl_days)
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> None:
        await users_repo.insert(ctx.db, doc, s)
        invitation_id = await links.create(
            ctx.db, Kind.INVITATION, doc["_id"], now=now, expires_at=expires_at, session=s
        )
        await emitter.user("user.invited", ev.UserInvited, doc, s, invitation_id=invitation_id)

    try:
        await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise EmailTaken() from exc
    return UserOut.of(doc)


@users.get("/{id}")
async def get_user(id: IdPath, admin: Admin, ctx: CtxDep) -> UserOut:
    return UserOut.of(await users_repo.require(ctx.db, id))


@users.patch("/{id}")
async def patch_user(id: IdPath, body: UserPatch, admin: Admin, ctx: CtxDep) -> UserOut:
    """Roles, organization, status, name and phone. Disabling logs the user out of every
    device at once (AUTH-11)."""
    current = await users_repo.require(ctx.db, id)
    changes: dict[str, Any] = {}
    for field in ("name", "phone"):
        value = getattr(body, field)
        if value is not None and value != current.get(field):
            changes[field] = value
    roles = sorted(set(body.roles)) if body.roles is not None else list(current["roles"])
    org_id = body.org_id if "org_id" in body.model_fields_set else current.get("org_id")
    if roles != sorted(current["roles"]) or org_id != current.get("org_id"):
        rules.check_roles(roles, org_id)
        if org_id and org_id != current.get("org_id"):
            await organizations.require(ctx.db, org_id)
        changes["roles"], changes["org_id"] = roles, org_id
    new_status = current["status"]
    if body.status is not None and body.status != current["status"]:
        action = rules.Action.DISABLE if body.status == "disabled" else rules.Action.ENABLE
        new_status = rules.transition(
            current["status"], action, has_password=bool(current.get("password_hash"))
        ).value
        changes["status"] = new_status
    rules.check_admin_keeps_access(admin.id, id, roles, new_status)
    if not changes:
        return UserOut.of(current)

    now = ctx.clock.now()
    ends_sessions = new_status == rules.Status.DISABLED or "roles" in changes
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await users_repo.update(
            ctx.db, id, changes, now=now, by=admin.id, session=s, expected_version=body.version
        )
        if ends_sessions:
            await sessions.revoke_users(ctx.db, [id], now, session=s)
        if new_status == rules.Status.DISABLED and current["status"] != new_status:
            await emitter.user("user.disabled", ev.UserDisabled, updated, s, before=current)
        else:
            await emitter.user("user.updated", ev.UserUpdated, updated, s, before=current,
                               changed_fields=sorted(changes))
        return updated

    updated = await ctx.tx(save)
    if ends_sessions:
        # Roles live in the access token, so a role change also needs a fresh sign-in.
        await revocation.revoke_user(ctx.redis, id, now)
    return UserOut.of(updated)


@users.post("/{id}/approve")
async def approve(id: IdPath, body: ApproveIn, admin: Admin, ctx: CtxDep) -> UserOut:
    """Link a pending client to an existing organization or create one (AUTH-3, AFD J1 4)."""
    if (body.org_id is None) == (body.new_organization is None):
        raise ValidationFailed("Give either org_id or new_organization", code="org_choice")
    current = await users_repo.require(ctx.db, id)
    rules.transition(current["status"], rules.Action.APPROVE)
    now = ctx.clock.now()
    new_org: dict[str, Any] | None = None
    org_id = body.org_id or ""
    if body.org_id:
        org = await organizations.require(ctx.db, body.org_id)
        if org["status"] != rules.OrgStatus.ACTIVE:
            raise ValidationFailed("Choose an active organization", code="org_inactive")
    if body.new_organization is not None:
        new_org = _org_doc(body.new_organization, now, admin.id)
        org_id = new_org["_id"]
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        if new_org is not None:
            await organizations.insert(ctx.db, new_org, s)
            await emitter.org("org.created", ev.OrgCreated, new_org, s)
        updated = await users_repo.update(
            ctx.db, id,
            {"status": rules.Status.ACTIVE.value, "roles": ["client"], "org_id": org_id},
            now=now, by=admin.id, session=s, expected_version=body.version or current["version"],
        )
        await emitter.user("user.approved", ev.UserApproved, updated, s, before=current)
        return updated

    try:
        updated = await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise _org_conflict(exc) from exc
    return UserOut.of(updated)


@users.post("/{id}/reject")
async def reject(id: IdPath, body: RejectIn, admin: Admin, ctx: CtxDep) -> UserOut:
    current = await users_repo.require(ctx.db, id)
    rules.transition(current["status"], rules.Action.REJECT)
    now = ctx.clock.now()
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await users_repo.update(
            ctx.db, id,
            {"status": rules.Status.REJECTED.value, "rejection_reason": body.reason},
            now=now, by=admin.id, session=s, expected_version=current["version"],
        )
        await emitter.user("user.rejected", ev.UserRejected, updated, s, before=current,
                           reason=body.reason)
        return updated

    return UserOut.of(await ctx.tx(save))


# --- Organizations (ORG-1, ORG-4) ------------------------------------------------------------


def _org_doc(body: OrgIn, now: Any, by: str) -> dict[str, Any]:
    return {
        "_id": new_id(), "name": body.name, "name_key": rules.org_name_key(body.name),
        "short_name": body.short_name, "external_id": body.external_id,
        "country": body.country, "contact_email": body.contact_email, "phone": body.phone,
        "address": body.address, "status": rules.OrgStatus.ACTIVE.value, "created_at": now,
        "updated_at": now, "created_by": by, "updated_by": by, "version": 1,
    }


@orgs.get("")
async def list_orgs(
    viewer: Reader,
    ctx: CtxDep,
    status_: Annotated[rules.OrgStatus | None, Query(alias="status")] = None,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Limit = 200,
) -> OrgPage:
    """Staff see every organization; a client sees only their own (rule 3)."""
    found = await organizations.search(
        ctx.db, viewer, status=status_.value if status_ else None, after=after, limit=limit + 1
    )
    more = len(found) > limit
    found = found[:limit]
    next_after = found[-1]["_id"] if more else None
    return OrgPage(items=[OrgOut.of(d) for d in found], next_after=next_after)


@orgs.get("/{id}")
async def get_org(id: IdPath, viewer: Reader, ctx: CtxDep) -> OrgOut:
    return OrgOut.of(await organizations.require(ctx.db, id, viewer))


@orgs.post("", status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgIn, admin: Admin, ctx: CtxDep) -> OrgOut:
    doc = _org_doc(body, ctx.clock.now(), admin.id)
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> None:
        await organizations.insert(ctx.db, doc, s)
        await emitter.org("org.created", ev.OrgCreated, doc, s)

    try:
        await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise _org_conflict(exc) from exc
    return OrgOut.of(doc)


@orgs.patch("/{id}")
async def patch_org(id: IdPath, body: OrgPatch, admin: Admin, ctx: CtxDep) -> OrgOut:
    """Deactivating blocks the organization's users from signing in; its data is kept (ORG-4)."""
    current = await organizations.require(ctx.db, id)
    changes = {
        k: v for k, v in body.model_dump(exclude={"version"}, exclude_unset=True).items()
        if v != current.get(k)
    }
    if "name" in changes:
        changes["name_key"] = rules.org_name_key(changes["name"])
    if not changes:
        return OrgOut.of(current)
    deactivating = changes.get("status") == rules.OrgStatus.INACTIVE
    emitter = ctx.emitter(admin)
    saved = await _save_org(ctx, emitter, id, current, changes, body.version, deactivating)
    return OrgOut.of(saved)


async def _save_org(
    ctx: Ctx,
    emitter: Emitter,
    org_id: str,
    current: dict[str, Any],
    changes: dict[str, Any],
    version: int,
    deactivating: bool,
) -> dict[str, Any]:
    now = ctx.clock.now()

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await organizations.update(
            ctx.db, org_id, changes, now=now, by=emitter.actor.user_id or "", session=s,
            expected_version=version,
        )
        if deactivating:
            member_ids = await users_repo.ids_in_org(ctx.db, org_id, session=s)
            await sessions.revoke_users(ctx.db, member_ids, now, session=s)
        await emitter.org("org.updated", ev.OrgUpdated, updated, s, before=current,
                          changed_fields=sorted(k for k in changes if k != "name_key"))
        return updated

    try:
        updated = await ctx.tx(save)
    except DuplicateKeyError as exc:
        raise _org_conflict(exc) from exc
    if deactivating:
        await revocation.revoke_org(ctx.redis, org_id, now)
    return updated

