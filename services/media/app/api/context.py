"""What every media route needs, gathered from app state once per request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from mms_common.auth import User, actor_for
from mms_common.events import Actor

from app.services import Services


@dataclass
class Ctx:
    request: Request
    svc: Services

    @property
    def request_id(self) -> str | None:
        return getattr(self.request.state, "request_id", None)

    def actor(self, user: User | None = None) -> Actor:
        return actor_for(self.request, user)


def get_ctx(request: Request) -> Ctx:
    return Ctx(request=request, svc=request.app.state.services)


CtxDep = Annotated[Ctx, Depends(get_ctx)]
