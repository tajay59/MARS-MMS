"""The end of every sign-in: a refresh session, the cookie, the audit event and the token
response. Shared by password login, the second step, enrolment at sign-in and invitations, so
there is one place that makes a session (TRD §6.1)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Response
from mms_common.ids import new_id
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import Ctx
from app.api.schemas import TokenResponse
from app.domain import mfa
from app.domain import users as rules
from app.domain.tokens import new_token
from app.events.publish import ev
from app.repo import sessions
from app.repo import users as users_repo


def window_changes(ctx: Ctx, user: dict[str, Any]) -> dict[str, Any]:
    """`mfa_grace_until` for a person who needs a second factor and has no window yet: the first
    sign-in after the release, or after a role change, starts it (decision W22-6)."""
    if mfa.needs_window(
        roles=user["roles"], enrolled=bool(user.get("totp")),
        grace_until=user.get("mfa_grace_until"), required_roles=ctx.settings.totp_required_roles,
    ):
        return {"mfa_grace_until": mfa.window_end(ctx.clock.now(), ctx.settings.totp_grace_days)}
    return {}


async def sign_in(
    ctx: Ctx,
    user: dict[str, Any],
    response: Response,
    *,
    changes: dict[str, Any] | None = None,
    via: str | None = None,
    extra: list[Any] | None = None,
    recovery_codes: list[str] | None = None,
) -> TokenResponse:
    """Make the session and answer. `changes` are written with `last_login_at` (bookkeeping, no
    version bump and no `user.updated`); `via` is `totp` or `recovery` after a second step;
    `extra(session)` callbacks run in the same transaction."""
    now = ctx.clock.now()
    raw = new_token()
    expires_at = now + timedelta(days=ctx.settings.refresh_ttl_days)
    fields: dict[str, Any] = {"last_login_at": now, **(changes or {})}
    email_hash = rules.email_hash(user["email"])
    emitter = ctx.emitter(user_id=user["_id"], name=user["name"], roles=list(user["roles"]))

    async def save(session: AsyncClientSession) -> dict[str, Any]:
        await sessions.create(
            ctx.db, user_id=user["_id"], raw=raw, family_id=new_id(), now=now,
            expires_at=expires_at, device_label=ctx.device_label(), session=session,
        )
        await users_repo.col(ctx.db).update_one(
            {"_id": user["_id"]}, {"$set": fields}, session=session
        )
        for step in extra or []:
            await step(session)
        await emitter.security(
            ev.LoginSucceeded(user_id=user["_id"], email_hash=email_hash, mfa=via),
            type_="auth.login_succeeded", user=user, email_hash=email_hash, session=session,
        )
        return {**user, **fields}

    fresh = await ctx.tx(save)
    ctx.set_refresh_cookie(response, raw)
    out = ctx.token_response(fresh, expires_at)
    out.recovery_codes = recovery_codes
    return out
