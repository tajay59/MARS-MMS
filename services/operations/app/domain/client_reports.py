"""A client's own report on a request (PRD CRP-1 to CRP-5; TRD 3.2; decisions W18-9, W18-10).
No I/O.

A client adds a report to a request by uploading one PDF (`pdf`) or by filling in an online form
(`form`). It starts as a draft only its author sees and can change; submitting it makes it
read-only for good and shows it to the organization and to staff (CRP-4). A form report is then
drawn as a PDF by the report service.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from enum import StrEnum
from typing import Any

from mms_common.errors import Conflict, ValidationFailed

from app.domain.requests.state import Status
from app.domain.stations.documents import FileFacts, check_file

MAX_TITLE = 200
MAX_SUMMARY = 10_000
MAX_OBSERVATION = 5_000
MAX_NOTES = 5_000
MAX_IMAGES = 10  # W18-10: printed as an appendix
MAX_FILE_BYTES = 25 * 1024 * 1024
EARLIEST_DATE = date(2000, 1, 1)

PDF_KINDS = frozenset({"pdf"})
IMAGE_KINDS = frozenset({"image"})

# A request that never reached the work, or was refused, has nothing to report on (W18-9). A
# Closed one can still take a report: a late one is real (CRP-1 "at any time", question 2).
NO_REPORTS = frozenset({Status.SUBMITTED, Status.DENIED, Status.CANCELLED})


class Kind(StrEnum):
    PDF = "pdf"
    FORM = "form"


class State(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class Render(StrEnum):
    """A form report's PDF: `none` for a PDF report and for a draft, `rendering` from submit
    until the report service says, then `ready` or `failed` (Try again submits it once more)."""

    NONE = "none"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"


def owner_ref(report_id: str) -> str:
    """What media files a client report's uploads under (TRD 5.3)."""
    return f"client_report:{report_id}"


def check_request(request_status: str) -> None:
    if Status(request_status) in NO_REPORTS:
        raise Conflict("This request can't take a report yet", code="request_not_reportable")


def clean_title(text: str, *, required: bool) -> str:
    title = " ".join(text.split())
    if required and not title:
        raise ValidationFailed("Give the report a title", code="required", field="title")
    if len(title) > MAX_TITLE:
        raise ValidationFailed(f"Keep the title under {MAX_TITLE} characters", code="too_long",
                               field="title")
    return title


def clean_text(text: str, *, limit: int, field: str) -> str:
    body = text.strip()
    if len(body) > limit:
        raise ValidationFailed(f"Keep this under {limit:,} characters", code="too_long",
                               field=field)
    return body


def check_date(value: date) -> date:
    if value < EARLIEST_DATE:
        raise ValidationFailed("That date is too far back", code="invalid", field="report_date")
    return value


def check_stations(wanted: Sequence[str], request_station_ids: Sequence[str]) -> list[str]:
    """Stations the report covers: each one belongs to the request, listed once."""
    unique = list(dict.fromkeys(wanted))
    own = set(request_station_ids)
    if any(s not in own for s in unique):
        raise ValidationFailed("A station is not part of this request", code="unknown_station",
                               field="station_ids")
    return unique


def check_observations(
    observations: Sequence[Mapping[str, str]], station_ids: Sequence[str]
) -> list[dict[str, str]]:
    """One note per station the report covers, in the order given; blank notes are dropped."""
    covered = set(station_ids)
    seen: set[str] = set()
    kept: list[dict[str, str]] = []
    for o in observations:
        sid = o["station_id"]
        if sid not in covered:
            raise ValidationFailed("That station is not covered by this report",
                                   code="unknown_station", field="observations")
        if sid in seen:
            raise ValidationFailed("Two notes for one station", code="duplicate",
                                   field="observations")
        seen.add(sid)
        text = clean_text(o["text"], limit=MAX_OBSERVATION, field="observations")
        if text:
            kept.append({"station_id": sid, "text": text})
    return kept


def check_image_ids(ids: Sequence[str]) -> list[str]:
    unique = list(dict.fromkeys(ids))
    if len(unique) > MAX_IMAGES:
        raise ValidationFailed(f"Attach up to {MAX_IMAGES} pictures", code="too_many_files",
                               field="image_ids")
    return unique


def check_upload(
    facts: FileFacts | None, *, report_id: str, user_id: str, kind: Kind, field: str
) -> FileFacts:
    """A clean file of the right kind this person uploaded for this report, within the size
    limit. A PDF report holds one PDF; a form report holds pictures."""
    checked = check_file(
        facts, owner=owner_ref(report_id), kinds=PDF_KINDS if kind is Kind.PDF else IMAGE_KINDS,
        user_id=user_id, ready_only=True, field=field,
    )
    if checked.size_bytes > MAX_FILE_BYTES:
        raise ValidationFailed(
            f"{checked.filename} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB",
            code="too_large", field=field,
        )
    return checked


def attachment(facts: FileFacts, media_id: str) -> dict[str, Any]:
    return {"media_id": media_id, "name": facts.filename, "size_bytes": facts.size_bytes}


def ready_to_submit(doc: Mapping[str, Any]) -> None:
    """What a report needs before it can be sent. Says which field is missing, so the page can
    point at it."""
    if not doc["title"]:
        raise ValidationFailed("Give the report a title", code="required", field="title")
    if not doc["station_ids"]:
        raise ValidationFailed("Choose the stations it covers", code="required",
                               field="station_ids")
    if doc["kind"] == Kind.PDF.value:
        if not doc.get("file"):
            raise ValidationFailed("Upload the PDF first", code="required", field="media_id")
        return
    form = doc["form"]
    if not form["summary"]:
        raise ValidationFailed("Write a summary", code="required", field="summary")


def can_edit(doc: Mapping[str, Any], user_id: str) -> bool:
    """CRP-4: only the author, and only while it is a draft."""
    return bool(doc["status"] == State.DRAFT.value and doc["created_by"] == user_id)


def media_ids(doc: Mapping[str, Any]) -> list[str]:
    """Every file the report holds, for the visibility request that shows them to the
    organization when it is submitted."""
    if doc["kind"] == Kind.PDF.value:
        return [doc["file"]["media_id"]] if doc.get("file") else []
    return [i["media_id"] for i in doc["form"]["images"]]


def render_after_submit(kind: str) -> Render:
    return Render.RENDERING if kind == Kind.FORM.value else Render.NONE


def can_submit_again(doc: Mapping[str, Any]) -> bool:
    """A form report whose PDF could not be drawn is sent for drawing once more. The report
    itself is kept as it was submitted."""
    return bool(
        doc["status"] == State.SUBMITTED.value and doc["kind"] == Kind.FORM.value
        and doc["render"] == Render.FAILED.value
    )
