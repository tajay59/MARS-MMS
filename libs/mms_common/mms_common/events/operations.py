"""Payloads of the events the operations service produces on `mms.operations.events`
(TRD §8.4). Phase 2 adds the stations module's events; requests and visits follow.

Message keys (TRD §8.1): `station_id` for station events, and for sensor and calibration
events of a unit that sits at a station. A unit in stock has no station, so its events are
keyed by `unit_id`. A sensor model has neither: its events are keyed by `model_id`.
`aggregate_version` is the version of the record named in `resource` (station, unit or
model), so a read model can apply events and snapshots in any order (§8.6).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mms_common.events.registry import register


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- station.* -------------------------------------------------------------------------------


class StationData(_Data):
    """The fields read models need: report's facts filter by organization, country, type and
    status (TRD §5.4). Also the shape of `/internal/snapshot/stations`."""

    station_id: str
    code: str
    name: str
    org_id: str
    country: str
    status: str
    type: str | None = None
    time_zone: str | None = None


@register("station.created")
class StationCreated(StationData):
    via: str = "api"  # api | import


@register("station.updated")
class StationUpdated(StationData):
    changed_fields: list[str]


@register("qr.regenerated")
class QrRegenerated(_Data):
    """A station's label code was replaced and the old one revoked (QR-7). Carries no token."""

    station_id: str
    code: str
    org_id: str


# --- sensor_model.* --------------------------------------------------------------------------


class SensorModelData(_Data):
    model_id: str
    kind: str
    manufacturer: str
    model: str
    parameters: list[str]
    default_calibration_interval_days: int | None = None


@register("sensor_model.created")
class SensorModelCreated(SensorModelData):
    pass


@register("sensor_model.updated")
class SensorModelUpdated(SensorModelData):
    changed_fields: list[str]


# --- sensor_unit.* ---------------------------------------------------------------------------


class SensorUnitData(_Data):
    unit_id: str
    serial: str
    model_id: str
    status: str
    needs_review: bool
    current_station_id: str | None = None
    calibration_due_at: datetime | None = None


@register("sensor_unit.created")
class SensorUnitCreated(SensorUnitData):
    via: str = "api"  # api | import | visit (SEN-5)


@register("sensor_unit.updated")
class SensorUnitUpdated(SensorUnitData):
    changed_fields: list[str]


# --- sensor.* (installation history, SEN-3) --------------------------------------------------


class InstallationData(_Data):
    installation_id: str
    unit_id: str
    serial: str
    model_id: str
    station_id: str
    parameter: str | None = None
    at: datetime
    unit_status: str  # the unit's status after the change
    visit_id: str | None = None  # set when a visit's sensor action did it (Phase 4)
    action_id: str | None = None


@register("sensor.installed")
class SensorInstalled(InstallationData):
    pass


@register("sensor.removed")
class SensorRemoved(InstallationData):
    reason: str | None = None


@register("sensor.application_reversed")
class SensorApplicationReversed(_Data):
    """A visit's sensor action was changed or removed and its effects undone (TRD §3.2.3)."""

    action_id: str
    visit_id: str
    station_id: str
    unit_ids: list[str]


# --- calibration.* ---------------------------------------------------------------------------


class CalibrationData(_Data):
    calibration_id: str
    unit_id: str
    station_id: str | None = None
    method: str
    at: datetime
    result: str
    due_at: datetime | None = None  # the unit's calibration due date after this record


@register("calibration.recorded")
class CalibrationRecorded(CalibrationData):
    pass


@register("calibration.voided")
class CalibrationVoided(CalibrationData):
    """Undone with its sensor action (TRD §3.2.3, Phase 4)."""

    reason: str


# --- document.*, config.* and media visibility (W6) --------------------------------------------


class DocumentData(_Data):
    """Documents are keyed by the station they belong to; a model's by `model_id`."""

    document_id: str
    scope: str  # model | station
    scope_id: str
    doc_type: str
    title: str
    client_visible: bool
    media_id: str


@register("document.uploaded")
class DocumentUploaded(DocumentData):
    version_label: str | None = None
    supersedes_id: str | None = None


@register("document.updated")
class DocumentUpdated(DocumentData):
    changed_fields: list[str]


@register("config.version_created")
class ConfigVersionCreated(_Data):
    station_id: str
    version: int
    file_count: int
    visit_id: str | None = None


@register("media.visibility_requested")
class MediaVisibilityRequested(_Data):
    """Operations asks media to show files to the owner organization (`org`) or hide them
    (`staff`). Media applies only the newest `visibility_version` per file (ADR-19)."""

    media_ids: list[str]
    visibility: str  # staff | org
    visibility_version: int


# --- request.* (W8) --------------------------------------------------------------------------


class RequestData(_Data):
    """The fields read models need (TRD §5.4 `request_facts`): organization, stations, category,
    priority and status. Keyed by `request_id`; `aggregate_version` is the request's version."""

    request_id: str
    ref: str  # MR-YYYY-NNNN
    org_id: str
    station_ids: list[str]
    category: str
    priority: str
    status: str
    # Added in W9 for the notification module (optional, so version 1 stands): the words a
    # notification needs and who asked, without a read from operations (rule 1).
    title: str | None = None
    created_by: str | None = None
    # Who is on the request now, so the notification module knows whom a comment is for
    assigned_staff_ids: list[str] = Field(default_factory=list)


@register("request.submitted")
class RequestSubmitted(RequestData):
    """A new request: from a client (Submitted) or an admin (Approved, `by_admin`)."""

    by_admin: bool = False


@register("request.updated")
class RequestUpdated(RequestData):
    changed_fields: list[str]


@register("request.approved")
class RequestApproved(RequestData):
    pass


@register("request.denied")
class RequestDenied(RequestData):
    reason: str  # the client sees it


@register("request.cancelled")
class RequestCancelled(RequestData):
    reason: str | None = None
    cancelled_by: str  # client | admin


@register("request.status_changed")
class RequestStatusChanged(RequestData):
    """Every status change, next to the specific event. `from_status` is null on creation."""

    from_status: str | None = None
    to_status: str
    reason: str | None = None


@register("request.assigned")
class RequestAssigned(RequestData):
    """Approved to Assigned: an admin chose the staff, or a technician `claimed` the request."""

    staff_ids: list[str]
    staff_names: list[str]
    claimed: bool
    by_id: str


@register("request.staff_changed")
class RequestStaffChanged(RequestData):
    """The people on an Assigned request changed and the status did not (an admin changed them,
    or one of several let go)."""

    staff_ids: list[str]
    staff_names: list[str]
    added: list[str]
    removed: list[str]


@register("request.released")
class RequestReleased(RequestData):
    """Assigned back to Approved: the last person let go, or an admin unassigned. The request
    is in the queue again."""

    released_ids: list[str]
    released_names: list[str]
    by_id: str


# --- comment.* (W9 slice 2) -------------------------------------------------------------------


class CommentFacts(RequestData):
    """A comment's event carries the request's facts too, so a consumer needs no read. It never
    carries the comment's text: an internal comment can't leak through a notification, and a
    comment that is edited or made internal later leaves nothing stale behind (W9-10)."""

    comment_id: str
    author_id: str
    author_name: str
    author_role: str  # client | technician | admin
    internal: bool
    attachment_count: int


@register("comment.added")
class CommentAdded(CommentFacts):
    pass


@register("comment.updated")
class CommentUpdated(CommentFacts):
    body_changed: bool
    internal_changed: bool


# --- visit.* (Phase 4 W10) --------------------------------------------------------------------


class StationOwner(_Data):
    station_id: str
    owner_staff_id: str


class VisitFacts(_Data):
    """What every visit event says about the visit and its request, so a consumer needs no read
    (rule 1): the notification text, who it is for and where it goes. Keyed by `request_id`
    (TRD §8.1) and versioned by the visit. Never holds the visit's notes."""

    visit_id: str
    ref: str  # VR-YYYY-NNNN-NN
    request_id: str
    request_ref: str  # MR-YYYY-NNNN
    org_id: str
    title: str | None = None  # the request's title
    created_by: str | None = None  # who made the request (the client who is told)
    status: str  # planned | started | ended | cancelled
    planned_start: datetime
    planned_end: datetime
    staff_ids: list[str]
    lead_staff_id: str
    station_ids: list[str]
    station_owners: list[StationOwner]
    # The zone of the first station: the one the visit's dates are written in (W10-1). Optional,
    # so version 1 of every visit event still holds
    time_zone: str | None = None


@register("visit.scheduled")
class VisitScheduled(VisitFacts):
    pass


@register("visit.rescheduled")
class VisitRescheduled(VisitFacts):
    """Dates, people, stations or owners of a planned visit changed."""

    changed_fields: list[str]


@register("visit.cancelled")
class VisitCancelled(VisitFacts):
    reason: str | None = None
    by_request: bool = False  # the request itself was cancelled


@register("visit.restored")
class VisitRestored(VisitFacts):
    pass


@register("visit.started")
class VisitStarted(VisitFacts):
    started_at: datetime


@register("visit.ended")
class VisitEnded(VisitFacts):
    """`sensor_actions` and `config_versions` stay empty until work records arrive (W11)."""

    ended_at: datetime
    additional_visit_required: bool
    follow_up_notes: str | None = None
    overrides: list[dict[str, str]] = Field(default_factory=list)
    sensor_actions: list[dict[str, object]] = Field(default_factory=list)
    config_versions: list[dict[str, object]] = Field(default_factory=list)


@register("visit.station_owner_changed")
class VisitStationOwnerChanged(VisitFacts):
    station_id: str
    from_staff_id: str  # `from` is a Python keyword
    to_staff_id: str
    # So the notification can say which station (optional: version 1 still holds)
    station_code: str | None = None
    station_name: str | None = None


@register("visit.station_arrived")
class VisitStationArrived(VisitFacts):
    station_id: str
    at: datetime


@register("visit.station_departed")
class VisitStationDeparted(VisitFacts):
    station_id: str
    at: datetime
