"""Which notifications also go by email, and who may choose (PRD NOT-3, NOT-4, Appendix B;
W9-13). No I/O.

In-app notifications are always on. Email is per type: the catalogue lists only the types a
person can receive by email, with their default. Account emails (registration outcome,
invitation, password reset) are always sent and are not in the catalogue (NOT-3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mms_common.errors import ValidationFailed

STAFF = frozenset({"technician", "admin"})


@dataclass(frozen=True)
class PrefType:
    key: str
    group: str
    label: str
    hint: str
    roles: frozenset[str]  # who can receive it by email
    default_on: frozenset[str]  # of those, the roles it starts on for


CATALOGUE: tuple[PrefType, ...] = (
    PrefType(
        "request.submitted", "Requests", "A client submits a request",
        "Sent to admins when a request needs a decision.",
        frozenset({"admin"}), frozenset({"admin"}),
    ),
    PrefType(
        "request.assigned", "Requests", "A request is assigned to you",
        "When an admin assigns you, or adds you to a request.",
        STAFF, STAFF,
    ),
    PrefType(
        "request.decided", "Requests", "Your request is approved or denied",
        "When an admin decides on a request you made.",
        frozenset({"client"}), frozenset({"client"}),
    ),
    PrefType(
        "request.cancelled", "Requests", "A request is cancelled",
        "One of yours, or one you are on, cancelled by someone else.",
        frozenset({"client", "technician", "admin"}), frozenset({"client"}),
    ),
    PrefType(
        "visit.scheduled", "Visits", "A visit is planned or its dates change",
        "For a request you made or a visit you attend.",
        frozenset({"client", "technician", "admin"}), frozenset({"client", "technician", "admin"}),
    ),
    PrefType(
        "visit.cancelled", "Visits", "A visit is cancelled",
        "For a request you made or a visit you attend.",
        frozenset({"client", "technician", "admin"}), frozenset({"client", "technician", "admin"}),
    ),
    PrefType(
        "request.client_review", "Review", "Work is ready for your review",
        "For a request you made, and reminders while nobody at your organization has answered.",
        frozenset({"client"}), frozenset({"client"}),
    ),
    PrefType(
        "request.reopened", "Review", "A client sends work back",
        "For a request you are on, with the client's reason.",
        STAFF, STAFF,
    ),
    PrefType(
        "report.closeout", "Review", "A corrected close-out report is ready",
        "When a report is corrected after a request closed. The first one is in the app only.",
        frozenset({"client"}), frozenset({"client"}),
    ),
    PrefType(
        "calibration.digest", "Calibration", "Weekly digest of calibrations due",
        "Mondays at 07:00. Overdue and due within 30 days.",
        frozenset({"admin"}), frozenset({"admin"}),
    ),
)
BY_KEY = {t.key: t for t in CATALOGUE}


def storage_key(key: str) -> str:
    """Mongo reads a dot in a field name as a path, so choices are stored as `request_assigned`."""
    return key.replace(".", "_")


_FROM_STORAGE = {storage_key(k): k for k in BY_KEY}


def from_storage(stored: str) -> str | None:
    """The type a stored name stands for; None for one the catalogue no longer has."""
    return _FROM_STORAGE.get(stored)


def types_for(roles: frozenset[str] | set[str]) -> list[PrefType]:
    """The types this person can turn on or off."""
    return [t for t in CATALOGUE if t.roles & roles]


def is_on(
    stored: Mapping[str, bool], key: str, roles: frozenset[str] | set[str]
) -> bool:
    """Whether `key` is emailed to a person with `roles`: their choice, else the default."""
    found = BY_KEY.get(key)
    if found is None or not found.roles & roles:
        return False  # not something this person can be emailed about
    if key in stored:
        return bool(stored[key])
    return bool(found.default_on & roles)


def check_choices(choices: Mapping[str, bool], roles: frozenset[str] | set[str]) -> dict[str, bool]:
    """Every key is one the person can choose; anything else is refused with its name."""
    allowed = {t.key for t in types_for(roles)}
    for key in choices:
        if key not in allowed:
            raise ValidationFailed("That is not something you can choose", code="unknown_type",
                                   field="email", key=key)
    return dict(choices)
