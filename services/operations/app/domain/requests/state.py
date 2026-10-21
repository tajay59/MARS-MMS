"""The request state machine (PRD §5.1, REQ-5; TRD §3.2.2). No I/O.

Two kinds of status change:

- **Actions** (`transition`): someone does something. Submitted, Approved, Denied, Cancelled,
  Reopened and Closed are set only this way, and every allowed move is one row of `RULES`.
- **Derived** (`derive.py`): from Assigned until closure the status follows the request's
  visits and visit reports, so no one sets it by hand.

A move the table does not list raises `Conflict` (409), whoever asks; a move that exists for
another kind of person raises `Forbidden`. Both are final: nothing here changes a record.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mms_common.errors import Conflict, Forbidden, ValidationFailed


class Status(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DENIED = "denied"
    ASSIGNED = "assigned"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    CLIENT_REVIEW = "client_review"
    REOPENED = "reopened"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Category(StrEnum):
    FAULT = "fault"
    COMMUNICATIONS = "communications"
    POWER = "power"
    CALIBRATION = "calibration"
    RELOCATION = "relocation"
    INSPECTION = "inspection"
    OTHER = "other"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Who(StrEnum):
    """The kind of person (or the system) behind an action."""

    CLIENT = "client"
    TECHNICIAN = "technician"
    ADMIN = "admin"
    SYSTEM = "system"


class Action(StrEnum):
    APPROVE = "approve"
    DENY = "deny"
    ASSIGN = "assign"  # an admin assigns, or a technician claims
    RELEASE = "release"  # the last assigned person lets go, or an admin unassigns: to the queue
    CANCEL = "cancel"
    ACCEPT = "accept"  # the client signs the work off (Phase 6)
    REJECT = "reject"  # the client sends it back (Phase 6)
    AUTO_CLOSE = "auto_close"  # no answer for 30 days (Phase 6)
    RETURN = "return"  # Reopened goes back to the same staff at once (Phase 6)


# Done: nothing moves a request out of these (the report service may still regenerate a
# close-out report, but the request stays as it is).
TERMINAL = frozenset({Status.DENIED, Status.CLOSED, Status.CANCELLED})
# From assignment until closure the status is derived from visits and reports (ADR-17).
DERIVED = frozenset({Status.ASSIGNED, Status.SCHEDULED, Status.IN_PROGRESS, Status.CLIENT_REVIEW})
# A client may edit or cancel their own request up to here (REQ-11).
CLIENT_EDITABLE = frozenset({Status.SUBMITTED, Status.APPROVED, Status.ASSIGNED})


@dataclass(frozen=True)
class Rule:
    to: Status
    who: frozenset[Who]
    reason: bool = False  # a reason is required
    own: bool = False  # a client may act only on their own organization's request


_ADMIN = frozenset({Who.ADMIN})
_CLIENT_OR_ADMIN = frozenset({Who.CLIENT, Who.ADMIN})
_STAFF = frozenset({Who.ADMIN, Who.TECHNICIAN})

RULES: dict[tuple[Status, Action], Rule] = {
    (Status.SUBMITTED, Action.APPROVE): Rule(Status.APPROVED, _ADMIN),
    (Status.SUBMITTED, Action.DENY): Rule(Status.DENIED, _ADMIN, reason=True),
    (Status.APPROVED, Action.ASSIGN): Rule(Status.ASSIGNED, _STAFF),
    # Letting go is open to the people who can take a request; a technician may release only a
    # request they are on (the route checks, as it knows the staff).
    (Status.ASSIGNED, Action.RELEASE): Rule(Status.APPROVED, _STAFF),
    # Cancelling: the client (own) or an admin up to Assigned; an admin only, with a reason,
    # once work is planned or under way, or waiting for the client (REQ-11).
    (Status.SUBMITTED, Action.CANCEL): Rule(Status.CANCELLED, _CLIENT_OR_ADMIN, own=True),
    (Status.APPROVED, Action.CANCEL): Rule(Status.CANCELLED, _CLIENT_OR_ADMIN, own=True),
    (Status.ASSIGNED, Action.CANCEL): Rule(Status.CANCELLED, _CLIENT_OR_ADMIN, own=True),
    (Status.SCHEDULED, Action.CANCEL): Rule(Status.CANCELLED, _ADMIN, reason=True),
    (Status.IN_PROGRESS, Action.CANCEL): Rule(Status.CANCELLED, _ADMIN, reason=True),
    (Status.CLIENT_REVIEW, Action.CANCEL): Rule(Status.CANCELLED, _ADMIN, reason=True),
    (Status.CLIENT_REVIEW, Action.ACCEPT): Rule(Status.CLOSED, frozenset({Who.CLIENT}), own=True),
    (Status.CLIENT_REVIEW, Action.REJECT): Rule(
        Status.REOPENED, frozenset({Who.CLIENT}), reason=True, own=True
    ),
    (Status.CLIENT_REVIEW, Action.AUTO_CLOSE): Rule(Status.CLOSED, frozenset({Who.SYSTEM})),
    (Status.REOPENED, Action.RETURN): Rule(Status.ASSIGNED, frozenset({Who.SYSTEM})),
}


def transition(
    current: Status,
    action: Action,
    who: Who,
    *,
    own: bool = True,
    reason: str | None = None,
    staff_count: int = 0,
) -> Status:
    """The status after `action`, or an error. `own` says whether a client's organization owns
    the request (a client on another organization's request is `Forbidden`; the repository
    normally never finds it, rule 4). `staff_count` is how many staff the request will have."""
    rule = RULES.get((current, action))
    if rule is None:
        raise Conflict(
            f"A request that is {current.value.replace('_', ' ')} can't be {_past(action)}",
            code="bad_transition",
        )
    if who not in rule.who or (who is Who.CLIENT and rule.own and not own):
        raise Forbidden()
    if rule.reason and not (reason and reason.strip()):
        raise ValidationFailed("Say why", code="reason_required", field="reason")
    if action is Action.ASSIGN and staff_count < 1:
        raise ValidationFailed("Pick at least one person", code="staff_required", field="staff_ids")
    return rule.to


def allowed(status: Status, who: Who, *, own: bool = True) -> list[Action]:
    """The actions `who` may take now, for the page to show only those buttons (viewers have no
    `Who` and so no actions). Reasons and staff are checked when the action is taken."""
    return [
        action
        for (current, action), rule in RULES.items()
        if current is status and who in rule.who
        and not (who is Who.CLIENT and rule.own and not own)
    ]


def _past(action: Action) -> str:
    return {
        Action.APPROVE: "approved", Action.DENY: "denied", Action.ASSIGN: "assigned",
        Action.RELEASE: "released",
        Action.CANCEL: "cancelled", Action.ACCEPT: "accepted", Action.REJECT: "rejected",
        Action.AUTO_CLOSE: "closed automatically", Action.RETURN: "returned",
    }[action]


# The timestamp a status sets (REQ-16: submitted, approved, first visit, client review, closed).
MILESTONES: dict[Status, str] = {
    Status.SUBMITTED: "submitted_at",
    Status.APPROVED: "approved_at",
    Status.ASSIGNED: "assigned_at",
    Status.CLIENT_REVIEW: "review_started_at",
    Status.CLOSED: "closed_at",
}
