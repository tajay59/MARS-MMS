"""The visit state machine (PRD VIS-1 to VIS-4, VIS-9; TRD §3.2; W10-2). No I/O.

Like the request table (`domain/requests/state.py`), every allowed move is one row of `RULES`
and nothing else decides. A move the table does not list raises `Conflict` (409), with the code
sync will report for it in Phase 5 (TRD §7.4): `visit_cancelled`, `already_ended` or
`bad_transition`. Nothing here changes a record.
"""

from __future__ import annotations

from enum import StrEnum

from mms_common.errors import Conflict


class VStatus(StrEnum):
    PLANNED = "planned"
    STARTED = "started"
    ENDED = "ended"
    CANCELLED = "cancelled"


class VAction(StrEnum):
    START = "start"
    CANCEL = "cancel"
    END = "end"
    RESTORE = "restore"  # an admin: a cancelled visit comes back (offline work was recorded on it)


RULES: dict[tuple[VStatus, VAction], VStatus] = {
    (VStatus.PLANNED, VAction.START): VStatus.STARTED,
    (VStatus.PLANNED, VAction.CANCEL): VStatus.CANCELLED,
    (VStatus.STARTED, VAction.END): VStatus.ENDED,
    (VStatus.CANCELLED, VAction.RESTORE): VStatus.PLANNED,
}

# A visit that is planned or started is "live": it holds its stations (W10-5), keeps its request
# Scheduled or In progress, and stops the request from being released (W10-7).
LIVE = frozenset({VStatus.PLANNED, VStatus.STARTED})


def move(current: VStatus, action: VAction) -> VStatus:
    to = RULES.get((current, action))
    if to is not None:
        return to
    if current is VStatus.CANCELLED:
        raise Conflict("This visit was cancelled", code="visit_cancelled")
    if current is VStatus.ENDED:
        raise Conflict("This visit has already ended", code="already_ended")
    raise Conflict(f"A visit that is {current.value} can't be {_past(action)}",
                   code="bad_transition")


def _past(action: VAction) -> str:
    return {VAction.START: "started", VAction.CANCEL: "cancelled", VAction.END: "ended",
            VAction.RESTORE: "restored"}[action]
