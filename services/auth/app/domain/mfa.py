"""Who must use a second factor, and until when they may sign in without one (decision W22-6).
No I/O here.

The rule applies at sign-in only, never to a live session: a person already signed in (a technician
in the field, an admin refreshing in the background) is never interrupted.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timedelta
from enum import StrEnum


class Gate(StrEnum):
    NOT_REQUIRED = "not_required"  # no role that needs it, and they have not opted in
    ENROLLED = "enrolled"  # has a second factor: the code step
    IN_WINDOW = "in_window"  # needs one, still inside the setup window: sign in and nudge
    BLOCKED = "blocked"  # needs one, window over: sign in only through enrolment


def required(roles: Collection[str], required_roles: Collection[str]) -> bool:
    return bool(set(roles) & set(required_roles))


def window_end(now: datetime, days: int) -> datetime:
    return now + timedelta(days=days)


def gate(
    *,
    roles: Collection[str],
    enrolled: bool,
    grace_until: datetime | None,
    now: datetime,
    required_roles: Collection[str],
) -> Gate:
    """`grace_until` must already be set for a person who needs a factor (see `needs_window`)."""
    if enrolled:
        return Gate.ENROLLED
    if not required(roles, required_roles):
        return Gate.NOT_REQUIRED
    if grace_until is not None and now < grace_until:
        return Gate.IN_WINDOW
    return Gate.BLOCKED


def needs_window(
    *, roles: Collection[str], enrolled: bool, grace_until: datetime | None,
    required_roles: Collection[str],
) -> bool:
    """The first sign-in after the release, or after a role change, starts the window."""
    return grace_until is None and not enrolled and required(roles, required_roles)
