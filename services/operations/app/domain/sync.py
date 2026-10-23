"""What `/sync` says about each operation a phone sends (TRD §7.3, §7.4; PRD OFF-5, OFF-7, OFF-11;
W14-2 to W14-5). No I/O.

A phone queues operations while it has no signal and sends them later, in order. Each one is run
by the same code that serves it online, so what can go wrong is already named: a route raises
`Conflict` or `Forbidden` (somebody else owns the station now, the visit was cancelled, the
element changed) or `ValidationFailed` or a failure of a service it called. This module turns
what was raised into one of five answers, and decides which later operations wait.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from mms_common.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed

# The newest payload shape this server reads, and the one before it (finding F8): an op queued by
# an older app still applies after an update; one from a newer app waits for this server's update
CURRENT_VERSION = 1
ACCEPTED_VERSIONS = frozenset({1})

MAX_OPS = 100

OP_TYPES = (
    "visit.start", "station.arrive", "station.depart", "visit.end",
    "element.create", "element.update", "element.delete",
    "element.media_add", "element.media_remove",
)

Status = Literal["applied", "duplicate", "conflict", "error", "skipped"]

# Codes a phone keeps its copy for and shows with Export (TRD §7.4); every other Conflict or
# Forbidden is a conflict too, with its own code
CONFLICT_CODES = frozenset({
    "not_owner", "not_editor", "not_attending", "not_started", "visit_cancelled",
    "already_ended", "locked", "element_changed", "element_deleted", "duplicate_id",
})
# Codes that mean "not yet": a file media has not finished receiving, a visit still being written.
# The phone asks again later without bothering the person
RETRYABLE_CODES = frozenset({"file_not_uploaded", "unknown_file", "update_required"})
# The ones that tell the lead and the admins (TRD §7.4: owner changed, visit cancelled)
NOTIFY_REASONS = frozenset({"not_owner", "not_editor", "visit_cancelled"})


@dataclass(frozen=True)
class Answer:
    op_id: str
    status: Status
    code: str | None = None
    message: str | None = None
    # A permanent error is shown to the person; a retryable one is tried again by the phone
    retryable: bool = False
    # The server's copy, for an element that changed under the phone
    current: dict[str, Any] | None = None
    # What the operation made, so the phone can replace its own copy with the server's
    result: dict[str, Any] | None = None
    duplicate: bool = False


def code_of(exc: AppError) -> str:
    """`Conflict("...", code="not_owner")` keeps its code in `extra`; the class has a default."""
    return str(exc.extra.get("code", exc.code))


def classify(op_id: str, exc: Exception) -> Answer:
    """What a raised error means for this operation."""
    if isinstance(exc, (Conflict, Forbidden)):
        code = code_of(exc)
        if code in RETRYABLE_CODES:
            return Answer(op_id, "error", code=code, message=exc.detail, retryable=True)
        current = exc.extra.get("current")
        return Answer(op_id, "conflict", code=code, message=exc.detail,
                      current=current if isinstance(current, dict) else None)
    if isinstance(exc, NotFound):
        # The visit, station or element is gone or was never the person's to see
        return Answer(op_id, "error", code="not_found", message="This was not found on the server")
    if isinstance(exc, ValidationFailed):
        return Answer(op_id, "error", code=code_of(exc), message=exc.detail)
    if isinstance(exc, AppError) and exc.status < 500:
        return Answer(op_id, "error", code=code_of(exc), message=exc.detail)
    # A service that was called is down, or something broke here: ask again later
    return Answer(op_id, "error", code="try_again", message="The server could not do this just now",
                  retryable=True)


def stale_version(op_id: str, version: int) -> Answer | None:
    """An op from an app newer than this server cannot be read yet; an older one than we read is
    refused for good."""
    if version in ACCEPTED_VERSIONS:
        return None
    if version > CURRENT_VERSION:
        return Answer(op_id, "error", code="update_required",
                      message="Made by a newer app: try again after the server updates",
                      retryable=True)
    return Answer(op_id, "error", code="unsupported_version",
                  message="This change was made by an app too old to read")


@dataclass
class Batch:
    """The rule that a failed operation stops the later ones of the same visit, and only those
    (TRD §7.3): another visit's work goes on."""

    blocked: set[str] = field(default_factory=set)

    def waits(self, visit_id: str) -> bool:
        return visit_id in self.blocked

    def settle(self, visit_id: str, answer: Answer) -> None:
        if answer.status not in ("applied", "duplicate"):
            self.blocked.add(visit_id)


def skipped(op_id: str) -> Answer:
    return Answer(op_id, "skipped", code="waiting",
                  message="An earlier change for this visit has not been saved yet", retryable=True)


def conflicts_to_report(
    answers: Iterable[tuple[str, str, Answer]],
) -> dict[tuple[str, str], list[str]]:
    """From `(visit_id, op_type, answer)`: the op types in conflict, by visit and reason."""
    found: dict[tuple[str, str], list[str]] = {}
    for visit_id, op_type, answer in answers:
        if answer.status == "conflict" and answer.code:
            found.setdefault((visit_id, answer.code), []).append(op_type)
    return found
