"""What every operations route needs, gathered from app state once per request."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from mms_common.auth import User, actor_for
from mms_common.mongo import in_transaction
from mms_common.time import Clock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings
from app.events.publish import Emitter
from app.repo.requests.staff_client import StaffApi
from app.repo.stations.media_client import MediaApi


@dataclass
class Ctx:
    request: Request
    settings: Settings
    clock: Clock
    client: AsyncMongoClient[dict[str, Any]]
    db: AsyncDatabase[dict[str, Any]]
    media: MediaApi
    staff: StaffApi
    # Run inside every transaction `tx` opens, after its body: `/sync` records an operation here,
    # so an operation and its record are one commit (TRD §7.3). Each hook must be safe to repeat.
    tx_hooks: tuple[Callable[[AsyncClientSession], Awaitable[None]], ...] = ()

    @property
    def request_id(self) -> str | None:
        return getattr(self.request.state, "request_id", None)

    def emitter(self, user: User | None = None) -> Emitter:
        return Emitter(self.db, self.clock, actor_for(self.request, user), self.request_id)

    async def tx[T](self, body: Callable[[AsyncClientSession], Awaitable[T]]) -> T:
        if not self.tx_hooks:
            return await in_transaction(self.client, body)

        async def with_hooks(s: AsyncClientSession) -> T:
            result = await body(s)
            for hook in self.tx_hooks:
                await hook(s)
            return result

        return await in_transaction(self.client, with_hooks)


def get_ctx(request: Request) -> Ctx:
    s = request.app.state
    return Ctx(
        request=request, settings=s.settings, clock=s.clock, client=s.mongo, db=s.db,
        media=s.media, staff=s.staff,
    )


CtxDep = Annotated[Ctx, Depends(get_ctx)]
