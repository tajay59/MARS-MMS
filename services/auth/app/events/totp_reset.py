"""Removing someone's second factor (lost phone). Used by the admin's route and the operator's
CLI, so both write the same record and the same audit event (W22-8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain import mfa
from app.domain import users as rules
from app.events.publish import Emitter, ev
from app.repo import sessions
from app.repo import users as users_repo


async def apply(
    tx: Any,
    db: Any,
    settings: Any,
    user: dict[str, Any],
    emitter: Emitter,
    *,
    now: datetime,
    via: str,
    by: str | None,
) -> dict[str, Any]:
    """Clear `totp` and `recovery_codes`, end every session, restart the setup window when the role
    needs a factor, and record `auth.totp_reset`. The caller then revokes access tokens in Redis."""
    changes: dict[str, Any] = {
        "totp": None,
        "recovery_codes": [],
        "mfa_grace_until": (
            mfa.window_end(now, settings.totp_grace_days)
            if mfa.required(user["roles"], settings.totp_required_roles) else None
        ),
    }

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        updated = await users_repo.update(db, user["_id"], changes, now=now, by=by, session=s)
        await sessions.revoke_users(db, [user["_id"]], now, session=s)
        await emitter.security(
            ev.TotpReset(user_id=user["_id"], via=via), type_="auth.totp_reset", user=updated,
            email_hash=rules.email_hash(user["email"]), session=s,
        )
        return updated

    result: dict[str, Any] = await tx(save)
    return result
