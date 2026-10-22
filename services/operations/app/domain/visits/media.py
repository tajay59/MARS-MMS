"""Photos and video on a visit (PRD VIS-5, VIS-10, MED-1; decisions W11-10, W11-13). No I/O here.

A station of a visit holds media in three phases: `before`, `during` and `after`. Any person
attending (or an admin) adds them while the visit is under way, or after it ended until its report
locks it (ADR-18: the owner writes the work record, but everyone on the visit takes photos). The
file lives in the media service; the visit keeps a small entry that names it. Files start
staff-only (ADR-19) and are shown to the client from the moment the visit ends, except an item a
staff member has hidden again.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from mms_common.errors import Conflict, Forbidden, NotFound, ValidationFailed

from app.domain.stations.documents import ARRIVED, FileFacts
from app.domain.visits.state import VStatus

PHASES = ("before", "during", "after")
KINDS = frozenset({"image", "video"})
MAX_CAPTION = 300
# A phone's clock can be a little ahead; a photo from next week is a mistake
FUTURE_SLACK = timedelta(days=1)

CHANGES = ("added", "captioned", "hidden", "shown", "removed")


def owner_ref(visit_id: str, station_id: str, phase: str) -> str:
    """The reference media files an upload under (TRD §5.3)."""
    return f"visit:{visit_id}:station:{station_id}:{phase}"


def parse_owner_ref(ref: str) -> tuple[str, str, str] | None:
    """`(visit_id, station_id, phase)` of a visit media reference, or None for any other owner."""
    parts = ref.split(":")
    if len(parts) == 5 and parts[0] == "visit" and parts[2] == "station" and parts[4] in PHASES:
        return parts[1], parts[3], parts[4]
    return None


def check_phase(phase: str) -> str:
    if phase not in PHASES:
        raise ValidationFailed(f"The phase can be: {', '.join(PHASES)}", code="bad_phase",
                               field="phase")
    return phase


def station_of(visit: Mapping[str, Any], station_id: str) -> Mapping[str, Any]:
    for station in visit["stations"]:
        if station["station_id"] == station_id:
            found: Mapping[str, Any] = station
            return found
    raise NotFound()


def entry_of(station: Mapping[str, Any], media_id: str) -> Mapping[str, Any]:
    for entry in station.get("media", []):
        if entry["media_id"] == media_id:
            found: Mapping[str, Any] = entry
            return found
    raise NotFound()


def check_can_change(visit: Mapping[str, Any], user_id: str, is_admin: bool) -> None:
    """Who and when: someone attending (or an admin), once the visit has started and until its
    report locks it. Refusals use the codes the work record does (`not_started`, `locked`...)."""
    if not (is_admin or user_id in visit["staff_ids"]):
        raise Forbidden("Only the people attending can do this", code="not_attending")
    status = VStatus(visit["status"])
    if status is VStatus.CANCELLED:
        raise Conflict("This visit was cancelled", code="visit_cancelled")
    if status is VStatus.PLANNED:
        raise Conflict("Start the visit first", code="not_started")
    if visit.get("locked"):
        raise Conflict("The visit report has been finalized. Ask an admin to reopen it",
                       code="locked")


def shared(visit: Mapping[str, Any]) -> bool:
    """Whether the client sees the visit's media now: from the end, never for a cancelled visit
    (W11-13)."""
    return VStatus(visit["status"]) is VStatus.ENDED


def check_caption(caption: str | None) -> str | None:
    if caption is None:
        return None
    text = caption.strip()
    if len(text) > MAX_CAPTION:
        raise ValidationFailed(f"A caption can be up to {MAX_CAPTION} characters",
                               code="caption_too_long", field="caption")
    return text or None


def check_captured_at(captured_at: datetime | None, now: datetime) -> datetime | None:
    if captured_at is not None and captured_at > now + FUTURE_SLACK:
        raise ValidationFailed("That time is in the future", code="captured_in_future",
                               field="captured_at")
    return captured_at


def check_file(facts: FileFacts | None, *, owner: str, user_id: str) -> FileFacts:
    """The uploader's own photo or video, uploaded for this station and phase, whole. It may
    still be going through media's checks and processing: the strip shows it as such."""
    if facts is None:
        raise ValidationFailed("That file wasn't found", code="unknown_file", field="media_id")
    if facts.owner_ref != owner:
        raise ValidationFailed("That file was uploaded for something else", code="wrong_owner",
                               field="media_id")
    if facts.uploaded_by != user_id:
        raise ValidationFailed("That file was uploaded by someone else", code="not_yours",
                               field="media_id")
    if facts.kind not in KINDS:
        raise ValidationFailed("Only photos and videos can go on a visit", code="wrong_kind",
                               field="media_id")
    if facts.status not in ARRIVED:
        raise ValidationFailed("The upload didn't finish", code="file_not_uploaded",
                               field="media_id")
    return facts


def new_entry(
    facts: FileFacts, *, media_id: str, phase: str, caption: str | None,
    captured_at: datetime | None, by: str, by_name: str, now: datetime,
    hidden: bool = False,
) -> dict[str, Any]:
    return {
        "media_id": media_id, "phase": phase, "kind": facts.kind, "filename": facts.filename,
        "caption": caption, "captured_at": captured_at, "added_by": by, "added_by_name": by_name,
        "added_at": now,
        "hidden": hidden,
    }


def clientside(station: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """What a client may be shown of a station's media (once the visit has ended): everything
    not hidden. The caller checks `shared` first."""
    return [e for e in station.get("media", []) if not e.get("hidden")]


def shared_ids(visit: Mapping[str, Any]) -> list[str]:
    """The media the end of the visit shows to the client."""
    return [e["media_id"] for s in visit["stations"] for e in clientside(s)]

