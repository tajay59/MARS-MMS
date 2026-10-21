"""Creating and editing a request (PRD REQ-1, REQ-2, REQ-4, REQ-11; TRD §5.2). No I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mms_common.errors import Forbidden, ValidationFailed

from app.domain.requests.state import CLIENT_EDITABLE, TERMINAL, Status, Who

MAX_STATIONS = 20
MAX_TITLE = 200
MAX_DESCRIPTION = 5000
EDITABLE_FIELDS = ("title", "description", "category", "priority", "station_ids")


def counter_key(year: int) -> str:
    """The `counters` document that numbers a year's requests (TRD §5.2)."""
    return f"MR-{year}"


def format_ref(year: int, seq: int) -> str:
    """`MR-2026-0042` (REQ-4). A year past 9,999 requests just gets a fifth digit."""
    return f"MR-{year}-{seq:04d}"


def year_of(when: datetime) -> int:
    return when.year  # the clock is UTC (rule 8)


def clean_text(value: str, field: str, *, maximum: int, required: bool = True) -> str:
    text = value.strip()
    if required and not text:
        raise ValidationFailed("This is required", code="required", field=field)
    if len(text) > maximum:
        raise ValidationFailed(
            f"Keep it under {maximum} characters", code="too_long", field=field
        )
    return text


def clean_stations(station_ids: Sequence[str]) -> list[str]:
    """One or more stations, each once, in the order given (REQ-1)."""
    unique = list(dict.fromkeys(station_ids))
    if not unique:
        raise ValidationFailed("Pick at least one station", code="stations_required",
                               field="station_ids")
    if len(unique) > MAX_STATIONS:
        raise ValidationFailed(f"Pick up to {MAX_STATIONS} stations", code="too_many_stations",
                               field="station_ids")
    return unique


def check_stations_belong(
    org_id: str, stations: Sequence[Mapping[str, Any] | None], station_ids: Sequence[str]
) -> None:
    """Every station exists and belongs to the request's organization. A station a client
    can't see comes back as `None`, so it reads the same as one that doesn't exist."""
    for station_id, station in zip(station_ids, stations, strict=True):
        if station is None or station.get("owner_org_id") != org_id:
            raise ValidationFailed(
                "That station isn't one of this organization's", code="unknown_station",
                field="station_ids", station_id=station_id,
            )


@dataclass(frozen=True)
class Edit:
    """What a person may change on a request, who may change it and when (REQ-11)."""

    changes: dict[str, object]


def check_can_edit(status: Status, who: Who) -> None:
    """A client edits their own request up to Assigned; an admin until it is done."""
    if who is Who.ADMIN:
        if status in TERMINAL:
            raise ValidationFailed(
                "This request is finished and can't be edited", code="request_finished"
            )
        return
    if who is Who.CLIENT:
        if status not in CLIENT_EDITABLE:
            raise ValidationFailed(
                "This request is already being worked on, so only an admin can change it",
                code="request_locked",
            )
        return
    raise Forbidden()


def changed_fields(before: dict[str, object], after: dict[str, object]) -> list[str]:
    return [f for f in EDITABLE_FIELDS if before.get(f) != after.get(f)]
