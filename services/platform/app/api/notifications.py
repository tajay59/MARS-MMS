"""Notifications (PRD NOT-1, NOT-2; TRD §3.5): the list with catch-up after a reconnect, and
marking as read. Everyone reads their own and only their own (rule 3: `user_id` is merged in
the repository, never taken from the request)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from mms_common.auth import User, require_roles
from mms_common.errors import NotFound
from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel

from app import realtime
from app.repo import notifications as repo

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

Reader = Annotated[User, Depends(require_roles())]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
# The groups the list's filter offers, each a fixed prefix of the notification types
GROUPS = {"requests": "request.", "comments": "comment.", "accounts": "account."}


class Entity(BaseModel):
    type: str
    id: str


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: str
    link: str
    entity: Entity
    read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread: int  # all of the person's unread, not only this page's
    next_before: str | None


class ReadAll(BaseModel):
    marked: int
    unread: int


def _db(request: Request) -> Any:
    return request.app.state.db


def _now(request: Request) -> datetime:
    now: datetime = request.app.state.clock.now()
    return now


@router.get("")
async def list_notifications(
    request: Request,
    user: Reader,
    after: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    before: Annotated[str | None, Query(pattern=UUID7_PATTERN)] = None,
    unread: bool = False,
    group: Annotated[Literal["requests", "comments", "accounts"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> NotificationPage:
    """Newest first. `after=<id>` returns everything newer than that notification: what a
    browser missed while it was offline or asleep (NOT-2). `before=<id>` pages further back."""
    db = _db(request)
    found = await repo.page(
        db, user.id, before=before, after=after, unread=unread,
        type_prefix=GROUPS[group] if group else None, limit=limit + 1,
    )
    more = len(found) > limit
    found = found[:limit]
    return NotificationPage(
        items=[NotificationOut(**realtime.out(d)) for d in found],
        unread=await repo.unread_count(db, user.id),
        next_before=found[-1]["_id"] if more and not after else None,
    )


@router.post("/read-all")
async def read_all(request: Request, user: Reader) -> ReadAll:
    db = _db(request)
    marked = await repo.mark_all_read(db, user.id, _now(request))
    return ReadAll(marked=marked, unread=await repo.unread_count(db, user.id))


@router.post("/{id}/read")
async def read_one(id: IdPath, request: Request, user: Reader) -> ReadAll:
    """Another person's notification, or none, is 404 (rule 4)."""
    db = _db(request)
    if not await repo.mark_read(db, user.id, id, _now(request)):
        raise NotFound()
    return ReadAll(marked=1, unread=await repo.unread_count(db, user.id))
