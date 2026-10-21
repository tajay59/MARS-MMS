"""Who is on a request: assigning, claiming and releasing (PRD REQ-7, W9-1 to W9-4). No I/O.

Every function answers one question: what changes. A change that moves the status goes
through `transition()` so the state table stays the one place that says which moves exist; a
change among staff while the request stays Assigned moves no status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain.requests.state import Action, Status, Who, transition

MAX_STAFF = 10
# Who can be put on a request: viewers never mutate (rule 5) and clients are not staff.
ASSIGNABLE_ROLES = frozenset({"technician", "admin"})


@dataclass(frozen=True)
class Person:
    id: str
    name: str


@dataclass(frozen=True)
class StaffChange:
    """The result of one assign, claim or release. `to` is the new status, or None when the
    request stays where it is and only its staff change."""

    staff: tuple[Person, ...]
    to: Status | None
    action: Action | None
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


def clean_staff_ids(ids: Sequence[str]) -> list[str]:
    unique = list(dict.fromkeys(ids))
    if not unique:
        raise ValidationFailed("Pick at least one person", code="staff_required",
                               field="staff_ids")
    if len(unique) > MAX_STAFF:
        raise ValidationFailed(f"Pick up to {MAX_STAFF} people", code="too_many_staff",
                               field="staff_ids")
    return unique


def check_assignable(ids: Sequence[str], found: Mapping[str, Mapping[str, Any]]) -> list[Person]:
    """Every person exists, is active and is a technician or an admin. The order given is kept."""
    people: list[Person] = []
    for staff_id in ids:
        user = found.get(staff_id)
        if (
            user is None
            or user["status"] != "active"
            or not ASSIGNABLE_ROLES & set(user["roles"])
        ):
            raise ValidationFailed(
                "That person can't be assigned to a request", code="not_assignable",
                field="staff_ids", staff_id=staff_id,
            )
        people.append(Person(staff_id, user["name"]))
    return people


def assign(
    status: Status, who: Who, current: Sequence[Person], wanted: Sequence[Person]
) -> StaffChange:
    """An admin sets the staff. From Approved the request becomes Assigned; while it is
    Assigned the staff change and nothing else does. Later the visits decide (Phase 4)."""
    if status is Status.ASSIGNED:
        if who is not Who.ADMIN:
            raise Forbidden()
        return _changed(wanted, current)
    to = transition(status, Action.ASSIGN, who, staff_count=len(wanted))
    return StaffChange(staff=tuple(wanted), to=to, action=Action.ASSIGN,
                       added=tuple(p.id for p in wanted))


def claim(status: Status, who: Who, me: Person, current: Sequence[Person]) -> StaffChange:
    """A technician (or an admin) takes a request from the queue for themselves."""
    if status is Status.ASSIGNED or current:
        raise Conflict("Someone else has claimed this request", code="already_assigned",
                       claimed_by=[p.name for p in current])
    to = transition(status, Action.ASSIGN, who, staff_count=1)
    return StaffChange(staff=(me,), to=to, action=Action.ASSIGN, added=(me.id,))


def release(
    status: Status, who: Who, me: Person, current: Sequence[Person]
) -> StaffChange:
    """A technician lets go of their own claim; an admin clears everyone. The request goes back
    to the queue when nobody is left, otherwise only the staff change."""
    if status is not Status.ASSIGNED:
        raise Conflict("Only a request that is assigned can be released", code="bad_transition")
    ids = {p.id for p in current}
    if who is Who.ADMIN:
        leaving = list(current)
    elif who is Who.TECHNICIAN and me.id in ids:
        leaving = [p for p in current if p.id == me.id]
    else:
        raise Forbidden()
    left = tuple(p for p in current if p not in leaving)
    if not left:
        to = transition(status, Action.RELEASE, who)
        return StaffChange(staff=(), to=to, action=Action.RELEASE,
                           removed=tuple(p.id for p in leaving))
    return StaffChange(staff=left, to=None, action=None, removed=tuple(p.id for p in leaving))


def _changed(wanted: Sequence[Person], current: Sequence[Person]) -> StaffChange:
    now = {p.id for p in current}
    after = {p.id for p in wanted}
    if now == after:
        raise Conflict("Those people are already on this request", code="no_change")
    return StaffChange(
        staff=tuple(wanted), to=None, action=None,
        added=tuple(p.id for p in wanted if p.id not in now),
        removed=tuple(p.id for p in current if p.id not in after),
    )


def actions_for(status: Status, who: Who | None, me_id: str, staff_ids: Sequence[str]) -> list[str]:
    """The staffing buttons the page offers this person now (claim, assign, release)."""
    out: list[str] = []
    if who not in (Who.ADMIN, Who.TECHNICIAN):
        return out
    if status is Status.APPROVED and not staff_ids:
        out.append("claim")
        if who is Who.ADMIN:
            out.append("assign")
    elif status is Status.ASSIGNED:
        if who is Who.ADMIN:
            out += ["assign", "release"]
        elif me_id in staff_ids:
            out.append("release")
    return out
