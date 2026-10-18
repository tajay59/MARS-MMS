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

from pydantic import BaseModel, ConfigDict

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
