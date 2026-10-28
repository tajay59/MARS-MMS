"""The client's answer to Client Review and the review clock (PRD REQ-12 to REQ-14; TRD 3.2.2,
11.3; decisions W18-2 to W18-8). No I/O.

A client accepts (with a drawn signature) or rejects (with a reason). Both carry `reviewing`,
the `review_started_at` the page read, so a client never signs a review that has since been
replaced by a corrected report. The clock reminds on the configured days and closes the request
when the last day passes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from mms_common.errors import Conflict

DAY = timedelta(days=1)
Outcome = Literal["accepted", "rejected", "auto_closed"]


def instant(value: datetime) -> datetime:
    """A time as Mongo keeps it: UTC, whole milliseconds. The page sends back the time it read,
    so two times are compared at that precision."""
    value = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def same_review(started: datetime | None, given: datetime) -> bool:
    return started is not None and instant(started) == instant(given)


def check_reviewing(started: datetime | None, given: datetime) -> None:
    """The client signs what they saw: if the review began again since (a report was reopened
    and made final once more), the answer is refused and the page shows the new review."""
    if not same_review(started, given):
        raise Conflict("The reports changed while you were reviewing. Please read them again",
                       code="review_changed")


def is_repeat(current: Mapping[str, Any], user_id: str, outcome: Outcome,
              reviewing: datetime) -> bool:
    """The same person sending the same answer for the same review again (the first answer
    was lost on the way): the stored result stands (W18-6)."""
    held = current.get("client_verification") or {}
    seen = held.get("reviewing")
    return (
        held.get("outcome") == outcome and held.get("by") == user_id
        and seen is not None and same_review(seen, reviewing)
    )


def auto_close_at(started: datetime, auto_close_days: float) -> datetime:
    return started + auto_close_days * DAY


@dataclass(frozen=True)
class Due:
    """What the clock does to one request now: `close`, `remind` (about day `day`, and every
    day in `mark` is recorded as sent), or nothing."""

    action: Literal["close", "remind"] | None
    day: float | None = None
    mark: tuple[float, ...] = ()


def due(
    now: datetime, started: datetime, sent: Iterable[float], reminder_days: Sequence[float],
    auto_close_days: float,
) -> Due:
    """Days are 24-hour periods since Client Review began (W18-7). After an outage that skipped
    several reminders only the latest is sent, and all of them are marked, so a client never
    gets three emails at once."""
    elapsed = (now - started) / DAY
    if elapsed >= auto_close_days:
        return Due("close")
    done = set(sent)
    overdue = [d for d in reminder_days if d <= elapsed and d not in done]
    if overdue:
        return Due("remind", day=max(overdue), mark=tuple(overdue))
    return Due(None)


def final_reports(visits: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The visit reports in force at the moment of the decision, so the close-out can say which
    versions the client accepted."""
    return [
        {"visit_id": v["_id"], "ref": v["ref"], "report_id": v.get("report_id"),
         "report_version": v.get("report_version")}
        for v in visits if v.get("report_status") == "final"
    ]


def decision(
    outcome: Outcome, *, user_id: str | None, name: str | None, at: datetime,
    reviewing: datetime | None, comment: str | None = None, reports: list[dict[str, Any]] | None,
    signature: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`requests.client_verification` (TRD 5.2). The drawn image lives only here and in the
    internal facts the report service reads; no event and no API answer carries it."""
    return {
        "outcome": outcome, "by": user_id, "by_name": name, "at": at, "reviewing": reviewing,
        "comment": comment, "reports": reports or [], "signature": signature,
    }


def signature(
    *, typed: str, image: bytes, attestation: str, ip: str | None, user_agent: str | None,
) -> dict[str, Any]:
    return {"typed_name": typed, "image": image, "attestation": attestation, "ip": ip,
            "user_agent": user_agent}
