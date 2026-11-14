"""The second factor (W22; PRD AUTH-14; TRD §6.1.1).

Sign-in: `POST /login` answers a challenge when the person has TOTP (or must set it up); these
routes finish it. Management, for staff who are signed in, lives under `/me/totp`. A wrong code
counts on the same per-account lock as a wrong password, and every answer says only that the code
is incorrect. No secret, code or hash is ever logged, put in an event or returned twice: the secret
and the recovery codes are shown once, in the answer that creates them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from mms_common.auth import User, require_roles
from mms_common.errors import Conflict, RateLimited, Unauthenticated, ValidationFailed
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api import signin
from app.api.context import Ctx, CtxDep
from app.api.schemas import (
    EnrolBeginIn,
    EnrolConfirmIn,
    LoginTotpIn,
    OneFactor,
    RecoveryCodesOut,
    TokenResponse,
    TotpBeginIn,
    TotpConfirmIn,
    TotpProofIn,
    TotpSetupOut,
)
from app.api.session_routes import AccountBlocked, AccountPending
from app.domain import mfa, recovery, totp
from app.domain import users as rules
from app.events.publish import Emitter, ev
from app.repo import mfa_challenges, organizations, sessions, throttle
from app.repo import totp as totp_repo
from app.repo import users as users_repo

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
Staff = Annotated[User, Depends(require_roles("admin", "technician", "viewer"))]


class TotpAlreadyOn(Conflict):
    code, title = "totp_enabled", "Two-step sign-in is already on"


class TotpNotSetUp(Conflict):
    code, title = "totp_not_enabled", "Two-step sign-in is not on"


class TotpRequired(Conflict):
    code, title = "totp_required", "Your role needs two-step sign-in, so it can't be turned off"


@dataclass(frozen=True)
class Factor:
    via: str  # totp | recovery
    remaining: int | None = None  # recovery codes left, after a recovery code


def _invalid_challenge() -> Unauthenticated:
    return Unauthenticated("Sign in again", reason="invalid_challenge")


def _wrong_code(signed_in: bool, field: str = "code") -> Exception:
    """A person with no session gets a 401 (the app shows the code step again); a signed-in one
    gets a field error, because a 401 there would look like an ended session."""
    if signed_in:
        return ValidationFailed(
            "The code is incorrect",
            errors=[{"loc": ["body", field], "msg": "The code is incorrect", "code": "wrong_code"}],
        )
    return Unauthenticated("The code is incorrect", reason="invalid_code")


async def _locked(ctx: Ctx, user: dict[str, Any]) -> None:
    if await throttle.is_locked(
        ctx.redis, rules.email_hash(user["email"]), ctx.settings.login_max_failures
    ):
        raise RateLimited(
            "Too many attempts, try again in 15 minutes", retry_after=ctx.settings.login_lock_s
        )


async def _failed(ctx: Ctx, user: dict[str, Any], reason: str) -> None:
    email_hash = rules.email_hash(user["email"])
    await throttle.record_failure(ctx.redis, email_hash, ctx.settings.login_lock_s)
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))

    async def save(s: AsyncClientSession) -> None:
        await emitter.security(
            ev.MfaFailed(user_id=user["_id"], email_hash=email_hash, reason=reason),
            type_="auth.mfa_failed", user=user, email_hash=email_hash, session=s,
        )

    await ctx.tx(save)


async def _check_totp(
    ctx: Ctx, user: dict[str, Any], secret: bytes, code: str, *, claim: bool, signed_in: bool
) -> None:
    """The code must belong to a step in the window and not be a replay. `claim`: record the step
    as used (enrolment has no earlier step to compare with)."""
    now_s = ctx.clock.now().timestamp()
    last = (user.get("totp") or {}).get("last_step") if claim else None
    step = totp.verify(secret, code, now_s, last)
    if step is None:
        replay = claim and totp.verify(secret, code, now_s, None) is not None
        await _failed(ctx, user, "replayed_code" if replay else "wrong_code")
        raise _wrong_code(signed_in)
    if claim and not await totp_repo.claim_step(ctx.db, user["_id"], step):
        await _failed(ctx, user, "replayed_code")
        raise _wrong_code(signed_in)


async def verify_factor(
    ctx: Ctx, user: dict[str, Any], body: OneFactor, *, signed_in: bool
) -> Factor:
    """A current code or an unused recovery code, for a person who has TOTP. Raises when the
    account is locked, or the factor is wrong or already used."""
    await _locked(ctx, user)
    if body.recovery_code is not None:
        found = recovery.find_unused(user.get("recovery_codes") or [], body.recovery_code)
        if found is None or not await totp_repo.claim_recovery(
            ctx.db, user["_id"], found, ctx.clock.now()
        ):
            await _failed(ctx, user, "wrong_recovery_code")
            raise _wrong_code(signed_in, "recovery_code")
        fresh = await users_repo.require(ctx.db, user["_id"])
        return Factor("recovery", recovery.remaining(fresh.get("recovery_codes")))
    sealed = (user.get("totp") or {}).get("secret_enc")
    secret = totp_repo.unseal(ctx.settings.totp_key_bytes, sealed, user["_id"]) if sealed else None
    if secret is None:
        await _failed(ctx, user, "wrong_code")
        raise _wrong_code(signed_in)
    await _check_totp(ctx, user, secret, body.code or "", claim=True, signed_in=signed_in)
    return Factor("totp")


def _factor_events(
    emitter: Emitter, user: dict[str, Any], factor: Factor
) -> list[Any]:
    if factor.via != "recovery":
        return []

    async def used(s: AsyncClientSession) -> None:
        await emitter.security(
            ev.RecoveryCodeUsed(user_id=user["_id"], remaining=factor.remaining or 0),
            type_="auth.recovery_code_used", user=user,
            email_hash=rules.email_hash(user["email"]), session=s,
        )

    return [used]


async def _signable(ctx: Ctx, purpose: str, token: str, *, count: bool) -> dict[str, Any]:
    """The user behind a challenge, who must still be allowed to sign in."""
    s = ctx.settings
    found = (
        await mfa_challenges.attempt(ctx.redis, token, purpose, s.mfa_challenge_tries)
        if count else await mfa_challenges.peek(ctx.redis, token, purpose)
    )
    user = await users_repo.get(ctx.db, found.user_id) if found else None
    if found is None or user is None:
        raise _invalid_challenge()
    org = await organizations.get(ctx.db, user["org_id"]) if user.get("org_id") else None
    outcome, _ = rules.login_outcome(user["status"], org["status"] if org else None)
    if outcome is rules.LoginOutcome.PENDING:
        raise AccountPending()
    if outcome is not rules.LoginOutcome.OK:
        raise AccountBlocked()
    return user


# --- Sign-in: the second step ----------------------------------------------------------------


@router.post("/login/totp")
async def login_totp(body: LoginTotpIn, ctx: CtxDep, response: Response) -> TokenResponse:
    user = await _signable(ctx, mfa_challenges.VERIFY, body.challenge, count=True)
    if not totp_repo.enabled(user):
        raise _invalid_challenge()
    factor = await verify_factor(ctx, user, body, signed_in=False)
    if not await mfa_challenges.consume(ctx.redis, body.challenge):
        raise _invalid_challenge()  # another request finished it first: one use
    await throttle.clear(ctx.redis, rules.email_hash(user["email"]))
    user = await users_repo.require(ctx.db, user["_id"])  # a recovery code was just used up
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))
    return await signin.sign_in(
        ctx, user, response, changes=signin.window_changes(ctx, user), via=factor.via,
        extra=_factor_events(emitter, user, factor),
    )


def _setup_out(secret: bytes, user: dict[str, Any], ctx: Ctx) -> TotpSetupOut:
    return TotpSetupOut(
        secret=totp.to_base32(secret),
        otpauth_uri=totp.otpauth_uri(secret, user["email"], ctx.settings.totp_issuer),
    )


async def _begin(ctx: Ctx, user: dict[str, Any]) -> TotpSetupOut:
    secret = totp.new_secret()
    sealed = totp_repo.seal(ctx.settings.totp_key_bytes, secret, user["_id"])
    await mfa_challenges.put_pending(ctx.redis, user["_id"], sealed)
    return _setup_out(secret, user, ctx)


async def _pending_secret(ctx: Ctx, user: dict[str, Any]) -> tuple[bytes, str]:
    sealed = await mfa_challenges.get_pending(ctx.redis, user["_id"])
    secret = totp_repo.unseal(ctx.settings.totp_key_bytes, sealed, user["_id"]) if sealed else None
    if sealed is None or secret is None:
        raise ValidationFailed(
            "Start again: the setup expired", errors=[{"loc": ["body"], "code": "setup_expired",
                                                      "msg": "Start again: the setup expired"}],
        )
    return secret, sealed


@router.post("/login/totp/enrol/begin")
async def enrol_begin(body: EnrolBeginIn, ctx: CtxDep) -> TotpSetupOut:
    """The password was right and the role needs a second factor the person has not set up
    (after the setup window): the challenge allows only these two routes."""
    user = await _signable(ctx, mfa_challenges.ENROL, body.challenge, count=False)
    if totp_repo.enabled(user):
        raise _invalid_challenge()
    return await _begin(ctx, user)


@router.post("/login/totp/enrol/confirm")
async def enrol_confirm(body: EnrolConfirmIn, ctx: CtxDep, response: Response) -> TokenResponse:
    user = await _signable(ctx, mfa_challenges.ENROL, body.challenge, count=True)
    if totp_repo.enabled(user):
        raise _invalid_challenge()
    await _locked(ctx, user)
    secret, sealed = await _pending_secret(ctx, user)
    await _check_totp(ctx, user, secret, body.code, claim=False, signed_in=False)
    if not await mfa_challenges.consume(ctx.redis, body.challenge):
        raise _invalid_challenge()
    await mfa_challenges.clear_pending(ctx.redis, user["_id"])
    await throttle.clear(ctx.redis, rules.email_hash(user["email"]))
    codes, records = recovery.generate()
    now = ctx.clock.now()
    fields = totp_repo.enrolment_fields(
        sealed, records, now, totp.step_at(now.timestamp())
    )
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))
    email_hash = rules.email_hash(user["email"])

    async def enrolled(s: AsyncClientSession) -> None:
        await emitter.security(
            ev.TotpEnrolled(user_id=user["_id"]), type_="auth.totp_enrolled", user=user,
            email_hash=email_hash, session=s,
        )

    return await signin.sign_in(
        ctx, user, response, changes=fields, via="totp", extra=[enrolled], recovery_codes=codes
    )


# --- Managing it, signed in ---------------------------------------------------------------------


async def _own_password(ctx: Ctx, user: dict[str, Any], password: str) -> None:
    ok = await asyncio.to_thread(ctx.hasher.verify, user.get("password_hash"), password)
    if not ok:
        raise ValidationFailed(
            "Password is incorrect",
            errors=[{"loc": ["body", "password"], "msg": "Password is incorrect",
                     "code": "wrong_password"}],
        )


@router.post("/me/totp/begin")
async def me_begin(body: TotpBeginIn, caller: Staff, ctx: CtxDep) -> TotpSetupOut:
    user = await users_repo.require(ctx.db, caller.id)
    await _own_password(ctx, user, body.password)
    if totp_repo.enabled(user):
        raise TotpAlreadyOn()
    return await _begin(ctx, user)


@router.post("/me/totp/confirm")
async def me_confirm(body: TotpConfirmIn, caller: Staff, ctx: CtxDep) -> RecoveryCodesOut:
    user = await users_repo.require(ctx.db, caller.id)
    if totp_repo.enabled(user):
        raise TotpAlreadyOn()
    await _locked(ctx, user)
    secret, sealed = await _pending_secret(ctx, user)
    await _check_totp(ctx, user, secret, body.code, claim=False, signed_in=True)
    await mfa_challenges.clear_pending(ctx.redis, user["_id"])
    codes, records = recovery.generate()
    now = ctx.clock.now()
    fields = totp_repo.enrolment_fields(sealed, records, now, totp.step_at(now.timestamp()))
    emitter = ctx.emitter(caller)

    async def save(s: AsyncClientSession) -> None:
        updated = await users_repo.update(
            ctx.db, user["_id"], fields, now=now, by=user["_id"], session=s
        )
        await emitter.security(
            ev.TotpEnrolled(user_id=user["_id"]), type_="auth.totp_enrolled", user=updated,
            email_hash=rules.email_hash(user["email"]), session=s,
        )

    await ctx.tx(save)  # other sessions stay: enabling a second factor is not a reason to end them
    return RecoveryCodesOut(recovery_codes=codes)


async def _proven(ctx: Ctx, caller: User, body: TotpProofIn) -> dict[str, Any]:
    user = await users_repo.require(ctx.db, caller.id)
    await _own_password(ctx, user, body.password)
    if not totp_repo.enabled(user):
        raise TotpNotSetUp()
    await verify_factor(ctx, user, body, signed_in=True)
    return user


@router.post("/me/totp/recovery-codes")
async def me_recovery_codes(body: TotpProofIn, caller: Staff, ctx: CtxDep) -> RecoveryCodesOut:
    """New codes replace all the old ones, used or not."""
    user = await _proven(ctx, caller, body)
    codes, records = recovery.generate()
    emitter = ctx.emitter(caller)

    async def save(s: AsyncClientSession) -> None:
        updated = await users_repo.update(
            ctx.db, user["_id"], {"recovery_codes": records}, now=ctx.clock.now(),
            by=user["_id"], session=s,
        )
        await emitter.security(
            ev.RecoveryCodesRegenerated(user_id=user["_id"]),
            type_="auth.recovery_codes_regenerated", user=updated,
            email_hash=rules.email_hash(user["email"]), session=s,
        )

    await ctx.tx(save)
    return RecoveryCodesOut(recovery_codes=codes)


@router.delete("/me/totp", status_code=status.HTTP_204_NO_CONTENT)
async def me_disable(body: TotpProofIn, caller: Staff, ctx: CtxDep) -> None:
    """Staff who opted in may turn it off. A role that requires it may not (W22-7)."""
    user = await users_repo.require(ctx.db, caller.id)
    if mfa.required(user["roles"], ctx.settings.totp_required_roles):
        raise TotpRequired()
    await _proven(ctx, caller, body)
    now = ctx.clock.now()
    keep = None
    raw = ctx.refresh_cookie()
    if raw:
        row = await sessions.find(ctx.db, raw)
        keep = row["family_id"] if row and row["user_id"] == user["_id"] else None
    emitter = ctx.emitter(caller)

    async def save(s: AsyncClientSession) -> None:
        updated = await users_repo.update(
            ctx.db, user["_id"], {"totp": None, "recovery_codes": []}, now=now,
            by=user["_id"], session=s,
        )
        # Other devices sign in again; this one keeps its session (as after a password change).
        await sessions.revoke_users(ctx.db, [user["_id"]], now, keep_family=keep, session=s)
        await emitter.security(
            ev.TotpDisabled(user_id=user["_id"]), type_="auth.totp_disabled", user=updated,
            email_hash=rules.email_hash(user["email"]), session=s,
        )

    await ctx.tx(save)

