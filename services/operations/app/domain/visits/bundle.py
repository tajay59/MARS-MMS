"""The field bundle's rules (TRD §3.2.1, §7; PRD OFF-1; W13-9). No I/O.

Preparing a visit downloads it to a phone. The rules here are small: which visits may be
prepared, and how the visit remembers where it is prepared (`prepared_on`), so the pages that
reschedule, cancel or change an owner can warn that unsynced work on a phone may come back as a
conflict (TRD §7.4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from mms_common.errors import Conflict, Forbidden

from app.domain.visits.schedule import can_attend
from app.domain.visits.state import VStatus

# Bumped when the bundle's shape changes in a way an older app cannot read (W13-9). A newer app
# reads older bundles; an older app refuses a newer one and asks for an update.
BUNDLE_VERSION = 1

# One entry per person and phone. Ten is more phones than anyone carries on one visit
PREPARED_LIMIT = 10

PREPARABLE = frozenset({VStatus.PLANNED.value, VStatus.STARTED.value})


class NotPreparable(Conflict):
    code, title = "visit_not_preparable", "This visit can't be prepared"


def check_attending(user_id: str, is_admin: bool, visit: Mapping[str, Any]) -> None:
    """The people attending (and an admin) prepare a visit; other staff can read it online."""
    if not can_attend(user_id, is_admin, visit):
        raise Forbidden("Only the people attending can do this", code="not_attending")


def check_preparable(visit: Mapping[str, Any]) -> None:
    """Only a planned or started visit is carried out, so only those are prepared. An ended
    visit's board is closed to new work on the phone; a cancelled one has no work to do."""
    if visit["status"] not in PREPARABLE:
        raise NotPreparable("Only a planned or started visit can be prepared")


def prepared_entry(*, user_id: str, user_name: str, device_id: str, at: datetime) -> dict[str, Any]:
    return {"user_id": user_id, "user_name": user_name, "device_id": device_id, "at": at}


def merge_prepared(
    existing: Sequence[Mapping[str, Any]], entry: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Preparing again from the same phone replaces its entry; the newest ten are kept."""
    kept = [
        dict(e) for e in existing
        if not (e["user_id"] == entry["user_id"] and e["device_id"] == entry["device_id"])
    ]
    kept.append(dict(entry))
    return kept[-PREPARED_LIMIT:]
