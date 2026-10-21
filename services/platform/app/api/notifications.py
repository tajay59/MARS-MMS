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
from pydantic import BaseModel, ConfigDict, StrictBool

from app import realtime
from app.domain import preferences
from app.repo import notifications as repo
from app.repo import preferences as preference_repo

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

Reader = Annotated[User, Depends(require_roles())]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
# The groups the list's filter offers, each a fixed prefix of the notification types
GROUPS = {"requests": "request.", "comments": "comment.", "accounts": "account.",
          "calibration": "calibration."}


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


class PreferenceItem(BaseModel):
    key: str
    label: str
    hint: str
    email: bool  # as it stands now: the person's choice, or the default


class PreferenceGroup(BaseModel):
    label: str
    items: list[PreferenceItem]


class Preferences(BaseModel):
    """Email choices for the types this person can be emailed about (NOT-4). In-app
    notifications are always on, and account emails are always sent (NOT-3)."""

    groups: list[PreferenceGroup]


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: dict[str, StrictBool]


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
    group: Annotated[Literal["requests", "comments", "accounts", "calibration"] | None,
                     Query()] = None,
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


def _view(roles: frozenset[str], stored: dict[str, bool]) -> Preferences:
    groups: dict[str, list[PreferenceItem]] = {}
    for kind in preferences.types_for(roles):
        groups.setdefault(kind.group, []).append(PreferenceItem(
            key=kind.key, label=kind.label, hint=kind.hint,
            email=preferences.is_on(stored, kind.key, roles),
        ))
    return Preferences(groups=[PreferenceGroup(label=k, items=v) for k, v in groups.items()])


@router.get("/preferences")
async def get_preferences(request: Request, user: Reader) -> Preferences:
    """NOT-4: what this person can choose, as it stands."""
    stored = await preference_repo.email_choices(_db(request), user.id)
    return _view(user.roles, stored)


@router.put("/preferences")
async def put_preferences(body: PreferencesIn, request: Request, user: Reader) -> Preferences:
    """NOT-4: save choices. Only types this person can be emailed about may be named; anything
    else is refused whole and nothing is saved."""
    db = _db(request)
    chosen = preferences.check_choices(body.email, user.roles)
    stored = await preference_repo.save_email_choices(db, user.id, chosen, _now(request))
    return _view(user.roles, stored)


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
