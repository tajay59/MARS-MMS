"""Public account routes under /api/v1/auth: register, login, refresh, logout, password
reset, invitation acceptance, and the caller's own profile (TRD §3.1, §6.1, §6.2; AFD J1, J2).

Every response here is `Cache-Control: no-store` (set in main.py). Tokens and passwords never
appear in logs, events or error bodies.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from mms_common.auth import User, require_roles, revocation
from mms_common.errors import AppError, Forbidden, RateLimited, Unauthenticated, ValidationFailed
from mms_common.ids import new_id
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.api.context import Ctx, CtxDep
from app.api.schemas import (
    Accepted,
    AcceptInvitationIn,
    LoginIn,
    Me,
    MePatch,
    RegisterIn,
    ResetConfirmIn,
    ResetRequestIn,
    TokenResponse,
)
from app.domain import users as rules
from app.domain.passwords import check_new_password
from app.domain.tokens import Refresh, decide, new_token, open_successor
from app.events.publish import ev
from app.repo import links, organizations, sessions, throttle
from app.repo import users as users_repo
from app.repo.links import Kind

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
AnyUser = Annotated[User, Depends(require_roles())]


class LinkExpired(AppError):
    status, code, title = 410, "link_expired", "This link has expired"


class AccountPending(Forbidden):
    code, title = "account_pending", "This account is waiting for approval"


class AccountBlocked(Forbidden):
    code, title = "account_blocked", "This account cannot sign in. Contact the service desk."


class SessionEnded(Unauthenticated):
    """The refresh failed. main.py's handler also clears the refresh cookie. `reason`:
    session_expired, session_revoked or account_blocked (the PWA's /login banner)."""

    def __init__(self, reason: str) -> None:
        super().__init__("Sign in again", reason=reason)


# --- Registration (AUTH-1, AUTH-2) ----------------------------------------------------------


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterIn, ctx: CtxDep) -> Accepted:
    """Always the same answer for a new or an existing email, so registering can't be used
    to find out who has an account."""
    email = rules.normalize_email(body.email)
    if not rules.valid_email(email):
        raise ValidationFailed(
            "Enter a valid email", errors=[{"loc": ["body", "email"], "msg": "Enter a valid email",
                                            "code": "invalid_email"}]
        )
    await check_new_password(body.password, ctx.breached)
    password_hash = await asyncio.to_thread(ctx.hasher.hash, body.password)
    if await users_repo.find_by_email(ctx.db, email) is not None:
        return Accepted(status="pending")
    now = ctx.clock.now()
    doc: dict[str, Any] = {
        "_id": new_id(),
        "email": email,
        "password_hash": password_hash,
        "name": body.name,
        "phone": body.phone,
        "time_zone": None,
        "theme": rules.Theme.SYSTEM.value,
        "roles": ["client"],
        "org_id": None,
        "proposed_org_name": body.organization_name,
        "status": rules.Status.PENDING.value,
        "rejection_reason": None,
        "last_login_at": None,
        "created_at": now,
        "updated_at": now,
        "created_by": None,
        "updated_by": None,
        "version": 1,
    }
    emitter = ctx.emitter(user_id=doc["_id"], name=body.name, roles=["client"])

    async def save(s: AsyncClientSession) -> None:
        await users_repo.insert(ctx.db, doc, s)
        await emitter.user(
            "user.registered", ev.UserRegistered, doc, s,
            proposed_org_name=body.organization_name,
        )

    try:
        await ctx.tx(save)
    except DuplicateKeyError:
        pass  # registered by a concurrent request: same answer
    return Accepted(status="pending")


# --- Login (AUTH-7, AUTH-10; TRD §6.1.1) ----------------------------------------------------


@router.post("/login")
async def login(body: LoginIn, ctx: CtxDep, response: Response) -> TokenResponse:
    s = ctx.settings
    email = rules.normalize_email(body.email)
    email_hash = rules.email_hash(email)
    if await throttle.is_locked(ctx.redis, email_hash, s.login_max_failures):
        raise RateLimited("Too many attempts, try again in 15 minutes", retry_after=s.login_lock_s)

    user = await users_repo.find_by_email(ctx.db, email)
    # Runs the full Argon2 check against a dummy hash when there's no such account.
    matched = await asyncio.to_thread(
        ctx.hasher.verify, user.get("password_hash") if user else None, body.password
    )
    if not matched or user is None:
        await throttle.record_failure(ctx.redis, email_hash, s.login_lock_s)
        reason = "wrong_password" if user else "unknown_email"
        await _login_failed(ctx, user, email_hash, reason)
        raise Unauthenticated("Email or password is incorrect", reason="invalid_credentials")

    org = await organizations.get(ctx.db, user["org_id"]) if user.get("org_id") else None
    outcome, blocked_by = rules.login_outcome(user["status"], org["status"] if org else None)
    if outcome is not rules.LoginOutcome.OK:
        await _login_failed(ctx, user, email_hash, blocked_by or "blocked")
        if outcome is rules.LoginOutcome.PENDING:
            raise AccountPending()
        raise AccountBlocked()

    await throttle.clear(ctx.redis, email_hash)
    now = ctx.clock.now()
    raw = new_token()
    expires_at = now + timedelta(days=s.refresh_ttl_days)
    changes: dict[str, Any] = {"last_login_at": now}
    if ctx.hasher.needs_rehash(user["password_hash"]):
        changes["password_hash"] = await asyncio.to_thread(ctx.hasher.hash, body.password)
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))

    async def save(session: AsyncClientSession) -> dict[str, Any]:
        await sessions.create(
            ctx.db, user_id=user["_id"], raw=raw, family_id=new_id(), now=now,
            expires_at=expires_at, device_label=ctx.device_label(), session=session,
        )
        # last_login_at is bookkeeping, not a profile change: no version bump, no user.updated.
        await users_repo.col(ctx.db).update_one(
            {"_id": user["_id"]}, {"$set": changes}, session=session
        )
        await emitter.security(
            ev.LoginSucceeded(user_id=user["_id"], email_hash=email_hash),
            type_="auth.login_succeeded", user=user, email_hash=email_hash, session=session,
        )
        return {**user, **changes}

    fresh = await ctx.tx(save)
    ctx.set_refresh_cookie(response, raw)
    return ctx.token_response(fresh, expires_at)


async def _login_failed(
    ctx: Ctx, user: dict[str, Any] | None, email_hash: str, reason: str
) -> None:
    emitter = (
        ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))
        if user else ctx.emitter()
    )

    async def save(s: AsyncClientSession) -> None:
        await emitter.security(
            ev.LoginFailed(user_id=user["_id"] if user else None, email_hash=email_hash,
                           reason=reason),
            type_="auth.login_failed", user=user, email_hash=email_hash, session=s,
        )

    await ctx.tx(save)


# --- Refresh (TRD §6.1: rotation, 30 s grace, reuse detection) ------------------------------


@router.post("/refresh")
async def refresh(ctx: CtxDep, response: Response) -> TokenResponse:
    raw = ctx.refresh_cookie()
    if not raw:
        raise Unauthenticated("Sign in required", reason="no_session")
    grace = timedelta(seconds=ctx.settings.refresh_grace_s)
    now = ctx.clock.now()
    row = await sessions.find(ctx.db, raw)
    decision = decide(row, now, grace)

    if decision is Refresh.ROTATE and row is not None:
        current = row
        user = await _active_user_or_end(ctx, current)
        successor = new_token()
        expires_at = now + timedelta(days=ctx.settings.refresh_ttl_days)

        async def rotate(s: AsyncClientSession) -> bool:
            return await sessions.rotate(
                ctx.db, current, raw, successor, now=now, expires_at=expires_at, session=s
            )

        if await ctx.tx(rotate):
            ctx.set_refresh_cookie(response, successor)
            return ctx.token_response(user, expires_at)
        # Another tab or the service worker rotated it a moment ago: take the grace path.
        row = await sessions.find(ctx.db, raw)
        decision = decide(row, now, grace)

    if decision is Refresh.GRACE and row is not None:
        found = await _follow_successor(ctx, raw, row, grace)
        if found is not None:
            successor, successor_row = found
            user = await _active_user_or_end(ctx, successor_row)
            ctx.set_refresh_cookie(response, successor)
            return ctx.token_response(user, successor_row["expires_at"])
        decision = Refresh.INVALID

    if decision is Refresh.REUSE and row is not None:
        family_id = row["family_id"]
        await sessions.revoke_family(ctx.db, family_id, now)
        owner = await users_repo.get(ctx.db, row["user_id"])
        if owner is not None:
            victim = owner
            emitter = ctx.emitter(user_id=victim["_id"], name=victim["name"],
                                  roles=list(victim["roles"]))

            async def record(s: AsyncClientSession) -> None:
                await emitter.security(
                    ev.TokenReuseDetected(user_id=victim["_id"], family_id=family_id),
                    type_="auth.token_reuse_detected", user=victim,
                    email_hash=rules.email_hash(victim["email"]), session=s,
                )

            await ctx.tx(record)
        raise SessionEnded("session_revoked")

    raise SessionEnded("session_expired")


async def _follow_successor(
    ctx: Ctx, raw: str, row: dict[str, Any], grace: timedelta
) -> tuple[str, dict[str, Any]] | None:
    """The live successor of a token rotated within the grace window, following a chain of
    quick rotations. None if it was revoked since (logout, reset, disabling, reuse)."""
    now = ctx.clock.now()
    current_raw, current = raw, row
    for _ in range(5):
        sealed = current.get("successor_enc")
        nxt = open_successor(current_raw, sealed) if sealed else None
        if nxt is None:
            return None
        nxt_row = await sessions.find(ctx.db, nxt)
        state = decide(nxt_row, now, grace)
        if state is Refresh.ROTATE and nxt_row is not None:
            return nxt, nxt_row
        if state is not Refresh.GRACE or nxt_row is None:
            return None
        current_raw, current = nxt, nxt_row
    return None


async def _active_user_or_end(ctx: Ctx, row: dict[str, Any]) -> dict[str, Any]:
    """Refresh fails, and the family is revoked, once the user is disabled or their org is
    deactivated (AUTH-11, ORG-4). The PWA then shows /login with a reason banner."""
    user = await users_repo.get(ctx.db, row["user_id"])
    org = await organizations.get(ctx.db, user["org_id"]) if user and user.get("org_id") else None
    if user is None:
        await sessions.revoke_family(ctx.db, row["family_id"], ctx.clock.now())
        raise SessionEnded("account_blocked")
    outcome = rules.login_outcome(user["status"], org["status"] if org else None)[0]
    if outcome is not rules.LoginOutcome.OK:
        await sessions.revoke_family(ctx.db, row["family_id"], ctx.clock.now())
        raise SessionEnded("account_blocked")
    return user


# --- Logout -----------------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(ctx: CtxDep, response: Response) -> None:
    """Works with the cookie alone, so an expired access token can't stop a logout."""
    raw = ctx.refresh_cookie()
    row = await sessions.find(ctx.db, raw) if raw else None
    ctx.clear_refresh_cookie(response)
    if row is None:
        return
    user = await users_repo.get(ctx.db, row["user_id"])
    now = ctx.clock.now()
    emitter = (
        ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))
        if user else ctx.emitter()
    )

    async def save(s: AsyncClientSession) -> None:
        await sessions.revoke_family(ctx.db, row["family_id"], now, session=s)
        if user is not None:
            await emitter.security(
                ev.Logout(user_id=user["_id"]), type_="auth.logout", user=user,
                email_hash=rules.email_hash(user["email"]), session=s,
            )

    await ctx.tx(save)


# --- Password reset (AUTH-8) ----------------------------------------------------------------


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_reset(body: ResetRequestIn, ctx: CtxDep) -> Accepted:
    """Always 202: "If that email is registered, a link is on its way" (AFD J2)."""
    email = rules.normalize_email(body.email)
    email_hash = rules.email_hash(email)
    user = await users_repo.find_by_email(ctx.db, email)
    if (
        user is None
        or not rules.can_reset_password(user["status"])
        or not await throttle.allow_reset_request(
            ctx.redis, email_hash, ctx.settings.reset_requests_per_hour
        )
    ):
        return Accepted(status="accepted")
    now = ctx.clock.now()
    expires_at = now + timedelta(seconds=ctx.settings.reset_ttl_s)
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))

    async def save(s: AsyncClientSession) -> None:
        reset_id = await links.create(
            ctx.db, Kind.RESET, user["_id"], now=now, expires_at=expires_at, session=s
        )
        await emitter.security(
            ev.PasswordResetRequested(user_id=user["_id"], reset_id=reset_id),
            type_="auth.password_reset_requested", user=user, email_hash=email_hash, session=s,
        )

    await ctx.tx(save)
    return Accepted(status="accepted")


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_reset(body: ResetConfirmIn, ctx: CtxDep) -> None:
    now = ctx.clock.now()
    link = await links.find_open(ctx.db, Kind.RESET, body.token, now)
    user = await users_repo.get(ctx.db, link["user_id"]) if link else None
    if link is None or user is None or not rules.can_reset_password(user["status"]):
        raise LinkExpired()
    await check_new_password(body.password, ctx.breached)
    password_hash = await asyncio.to_thread(ctx.hasher.hash, body.password)
    new_status = rules.transition(user["status"], rules.Action.RESET_PASSWORD)
    email_hash = rules.email_hash(user["email"])
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))

    async def save(s: AsyncClientSession) -> None:
        if not await links.use(ctx.db, Kind.RESET, link["_id"], now, s):
            raise LinkExpired()
        changes: dict[str, Any] = {"password_hash": password_hash, "status": new_status.value}
        updated = await users_repo.update(ctx.db, user["_id"], changes, now=now,
                                          by=user["_id"], session=s)
        await sessions.revoke_users(ctx.db, [user["_id"]], now, session=s)
        await emitter.security(
            ev.PasswordReset(user_id=user["_id"], email_hash=email_hash),
            type_="auth.password_reset", user=updated, email_hash=email_hash, session=s,
        )
        if user["status"] != new_status:
            await emitter.user("user.updated", ev.UserUpdated, updated, s, before=user,
                               changed_fields=["status"])

    await ctx.tx(save)
    # Logged out of every device, including access tokens still within their 15 minutes.
    await revocation.revoke_user(ctx.redis, user["_id"], now)
    await throttle.clear(ctx.redis, email_hash)


# --- Invitations (AUTH-6) -------------------------------------------------------------------


@router.post("/invitations/accept")
async def accept_invitation(
    body: AcceptInvitationIn, ctx: CtxDep, response: Response
) -> TokenResponse:
    """Sets the password and signs the user in: they land on their dashboard (AFD J1)."""
    now = ctx.clock.now()
    link = await links.find_open(ctx.db, Kind.INVITATION, body.token, now)
    user = await users_repo.get(ctx.db, link["user_id"]) if link else None
    if link is None or user is None or user["status"] != rules.Status.INVITED:
        raise LinkExpired()
    org = await organizations.get(ctx.db, user["org_id"]) if user.get("org_id") else None
    if org is not None and org["status"] != rules.OrgStatus.ACTIVE:
        raise AccountBlocked()
    await check_new_password(body.password, ctx.breached)
    password_hash = await asyncio.to_thread(ctx.hasher.hash, body.password)
    new_status = rules.transition(user["status"], rules.Action.ACCEPT_INVITATION)
    raw = new_token()
    expires_at = now + timedelta(days=ctx.settings.refresh_ttl_days)
    email_hash = rules.email_hash(user["email"])
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        if not await links.use(ctx.db, Kind.INVITATION, link["_id"], now, s):
            raise LinkExpired()
        updated = await users_repo.update(
            ctx.db, user["_id"],
            {"password_hash": password_hash, "status": new_status.value, "last_login_at": now},
            now=now, by=user["_id"], session=s,
        )
        await sessions.create(
            ctx.db, user_id=user["_id"], raw=raw, family_id=new_id(), now=now,
            expires_at=expires_at, device_label=ctx.device_label(), session=s,
        )
        await emitter.user("user.updated", ev.UserUpdated, updated, s, before=user,
                           changed_fields=["status", "password"])
        await emitter.security(
            ev.LoginSucceeded(user_id=user["_id"], email_hash=email_hash),
            type_="auth.login_succeeded", user=updated, email_hash=email_hash, session=s,
        )
        return updated

    updated = await ctx.tx(save)
    ctx.set_refresh_cookie(response, raw)
    return ctx.token_response(updated, expires_at)


# --- My profile (AUTH-13, D2 theme) ---------------------------------------------------------


@router.get("/me")
async def get_me(user: AnyUser, ctx: CtxDep) -> Me:
    return Me.of(await users_repo.require(ctx.db, user.id))


@router.patch("/me")
async def patch_me(body: MePatch, user: AnyUser, ctx: CtxDep) -> Me:
    """Name, phone, time zone, theme and password. Viewers may edit their own profile."""
    current = await users_repo.require(ctx.db, user.id)
    changes: dict[str, Any] = {}
    changed: list[str] = []
    for field in ("name", "phone", "theme"):
        value = getattr(body, field)
        if value is not None and value != current.get(field):
            changes[field] = value
            changed.append(field)
    if body.time_zone is not None and body.time_zone != current.get("time_zone"):
        if not rules.valid_time_zone(body.time_zone):
            raise ValidationFailed(
                "Unknown time zone",
                errors=[{"loc": ["body", "time_zone"], "msg": "Unknown time zone",
                         "code": "invalid_time_zone"}],
            )
        changes["time_zone"] = body.time_zone
        changed.append("time_zone")
    if body.new_password is not None:
        ok = await asyncio.to_thread(
            ctx.hasher.verify, current.get("password_hash"), body.current_password or ""
        )
        if not ok:
            raise ValidationFailed(
                "Current password is incorrect",
                errors=[{"loc": ["body", "current_password"],
                         "msg": "Current password is incorrect", "code": "wrong_password"}],
            )
        await check_new_password(body.new_password, ctx.breached, field="new_password")
        changes["password_hash"] = await asyncio.to_thread(ctx.hasher.hash, body.new_password)
        changed.append("password")
    if not changes:
        return Me.of(current)

    now = ctx.clock.now()
    keep_family = None
    raw = ctx.refresh_cookie()
    if "password" in changed and raw:
        row = await sessions.find(ctx.db, raw)
        keep_family = row["family_id"] if row and row["user_id"] == user.id else None
    emitter = ctx.emitter(user)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await users_repo.update(ctx.db, user.id, changes, now=now, by=user.id, session=s)
        if "password" in changed:
            # Other devices sign in again; this one keeps its session.
            await sessions.revoke_users(ctx.db, [user.id], now, keep_family=keep_family, session=s)
        await emitter.user("user.updated", ev.UserUpdated, updated, s, before=current,
                           changed_fields=changed)
        return updated

    return Me.of(await ctx.tx(save))
