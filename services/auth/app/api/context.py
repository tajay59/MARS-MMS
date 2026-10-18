"""What every auth route needs, gathered from app state once per request."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from mms_common.auth import User, actor_for
from mms_common.auth.tokens import SigningKey, issue_access
from mms_common.mongo import in_transaction
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app.api.schemas import Me, TokenResponse
from app.config import Settings
from app.domain.passwords import BreachedCheck, Hasher
from app.events.publish import Emitter

COOKIE_PATH = "/api/v1/auth"


@dataclass
class Ctx:
    request: Request
    settings: Settings
    clock: Clock
    client: AsyncMongoClient[dict[str, Any]]
    db: AsyncDatabase[dict[str, Any]]
    redis: Redis
    signing: SigningKey
    hasher: Hasher
    breached: BreachedCheck

    @property
    def request_id(self) -> str | None:
        return getattr(self.request.state, "request_id", None)

    def emitter(self, user: User | None = None, **actor: Any) -> Emitter:
        return Emitter(self.db, self.clock, actor_for(self.request, user, **actor), self.request_id)

    async def tx[T](self, body: Callable[[AsyncClientSession], Awaitable[T]]) -> T:
        return await in_transaction(self.client, body)

    @property
    def cookie_name(self) -> str:
        # __Secure- makes browsers refuse the cookie unless it is Secure and came over HTTPS.
        return "__Secure-mms_refresh" if self.settings.cookie_secure else "mms_refresh"

    def refresh_cookie(self) -> str | None:
        return self.request.cookies.get(self.cookie_name)

    def set_refresh_cookie(self, response: Response, raw: str) -> None:
        response.set_cookie(
            self.cookie_name,
            raw,
            max_age=int(timedelta(days=self.settings.refresh_ttl_days).total_seconds()),
            path=COOKIE_PATH,
            secure=self.settings.cookie_secure,
            httponly=True,
            samesite="strict",
        )

    def clear_refresh_cookie(self, response: Response) -> None:
        response.delete_cookie(
            self.cookie_name,
            path=COOKIE_PATH,
            secure=self.settings.cookie_secure,
            httponly=True,
            samesite="strict",
        )

    def token_response(self, user: dict[str, Any], refresh_expires_at: Any) -> TokenResponse:
        access = issue_access(
            self.signing,
            clock=self.clock,
            user_id=user["_id"],
            roles=list(user["roles"]),
            org_id=user.get("org_id"),
            name=user["name"],
        )
        return TokenResponse(
            access_token=access,
            expires_in=15 * 60,
            refresh_expires_at=refresh_expires_at,
            user=Me.of(user),
        )

    def device_label(self) -> str | None:
        agent = self.request.headers.get("User-Agent")
        return agent[:120] if agent else None


def get_ctx(request: Request) -> Ctx:
    s = request.app.state
    return Ctx(
        request=request,
        settings=s.settings,
        clock=s.clock,
        client=s.mongo,
        db=s.db,
        redis=s.redis,
        signing=s.signing,
        hasher=s.hasher,
        breached=s.breached,
    )


CtxDep = Annotated[Ctx, Depends(get_ctx)]
