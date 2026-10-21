"""Internal-network routes. Nginx never routes `/internal/` or `/.well-known/` (TRD §2.1)."""

from __future__ import annotations

import base64
import binascii
import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request
from mms_common.auth import ServicePrincipal, require_service
from mms_common.auth.tokens import SERVICE_TTL, issue_service
from mms_common.errors import NotFound, Unauthenticated
from mms_common.ids import UUID7_PATTERN
from mms_common.snapshot import SnapshotPage, page

from app.api.context import CtxDep
from app.api.schemas import (
    AccountLinkIn,
    AccountLinkOut,
    ServiceTokenOut,
    UserLookupIn,
    UserLookupOut,
    UserRefOut,
)
from app.api.session_routes import LinkExpired
from app.domain import users as rules
from app.events.publish import org_data, user_data
from app.repo import keys, links
from app.repo import users as users_repo
from app.repo.links import Kind

router = APIRouter(tags=["internal"])

Platform = Annotated[ServicePrincipal, Depends(require_service("platform"))]
Operations = Annotated[ServicePrincipal, Depends(require_service("operations"))]
SnapshotReader = Annotated[
    ServicePrincipal, Depends(require_service("platform", "operations", "report"))
]


@router.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks(ctx: CtxDep) -> dict[str, Any]:
    return {"keys": await keys.published(ctx.db, ctx.clock.now())}


@router.post("/internal/service-token")
async def service_token(request: Request, ctx: CtxDep) -> ServiceTokenOut:
    """HTTP Basic with the service's name and secret (a Docker secret, TRD §6.4)."""
    name, secret = _basic(request.headers.get("Authorization", ""))
    expected = ctx.settings.service_secrets.get(name)
    if not expected or not hmac.compare_digest(expected.encode(), secret.encode()):
        raise Unauthenticated("Unknown service or wrong secret")
    token = issue_service(ctx.signing, clock=ctx.clock, service=name)
    return ServiceTokenOut(access_token=token, expires_in=int(SERVICE_TTL.total_seconds()))


def _basic(header: str) -> tuple[str, str]:
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic":
        raise Unauthenticated()
    try:
        name, _, secret = base64.b64decode(value, validate=True).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise Unauthenticated() from exc
    return name, secret


@router.post("/internal/account-links")
async def account_link(body: AccountLinkIn, svc: Platform, ctx: CtxDep) -> AccountLinkOut:
    """Mint the link for a reset or invitation email at the moment it is sent. The token is
    never in an event; minting again replaces it, so only the newest email's link works."""
    kind = Kind(body.kind)
    now = ctx.clock.now()
    minted = await links.mint(ctx.db, kind, body.id, now)
    user = await users_repo.get(ctx.db, minted[1]["user_id"]) if minted else None
    wanted = rules.Status.INVITED if kind is Kind.INVITATION else None
    if (
        minted is None
        or user is None
        or (wanted and user["status"] != wanted)
        or (kind is Kind.RESET and not rules.can_reset_password(user["status"]))
    ):
        raise LinkExpired()
    raw, row = minted
    path = "invite" if kind is Kind.INVITATION else "reset-password"
    return AccountLinkOut(
        url=f"{ctx.settings.app_url.rstrip('/')}/{path}/{raw}",
        email=user["email"],
        name=user["name"],
        expires_at=row["expires_at"],
    )


@router.post("/internal/users/lookup")
async def lookup_users(body: UserLookupIn, svc: Operations, ctx: CtxDep) -> UserLookupOut:
    """Name, roles and status for up to 50 people, for operations to check who may be assigned
    to a request (W9-2). People who do not exist are left out."""
    found = await users_repo.get_many(ctx.db, list(dict.fromkeys(body.ids)))
    return UserLookupOut(users=[
        UserRefOut(id=d["_id"], name=d["name"], roles=sorted(d["roles"]), status=d["status"])
        for d in found
    ])


@router.get("/internal/snapshot/{entity}")
async def snapshot(
    svc: SnapshotReader,
    ctx: CtxDep,
    entity: Annotated[str, Path(pattern="^(users|organizations)$")],
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> SnapshotPage:
    """Current state for read-model backfill (TRD §8.6), shaped like the events' data."""
    if entity == "users":
        result = await page(ctx.db["users"], after=after, limit=limit)
        items = [{**user_data(d), "aggregate_version": d["version"]} for d in result.items]
    elif entity == "organizations":
        result = await page(ctx.db["organizations"], after=after, limit=limit)
        items = [{**org_data(d), "aggregate_version": d["version"]} for d in result.items]
    else:  # pragma: no cover - the path pattern rules it out
        raise NotFound()
    return SnapshotPage(items=items, next_after=result.next_after)
