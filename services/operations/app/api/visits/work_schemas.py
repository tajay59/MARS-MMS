"""The work record's request and response bodies (PRD VIS-7; TRD §5.4 `WorkRecord`; W11-1, W11-4).

Everything is typed and bounded (rule 12): an enum for each choice, a length for each text, a
UUIDv7 for each entry made on a device (rule 9). The server decides `version`, `updated_by` and
`updated_at`; the template copy is the server's too.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from mms_common.ids import UUID7_PATTERN
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.api.stations.schemas import Reading, ReferenceInstrument

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Line = Annotated[str, StringConstraints(max_length=1000)]
Long = Annotated[str, StringConstraints(max_length=4000)]
Short = Annotated[str, StringConstraints(max_length=200)]

Condition = Literal["operational", "degraded", "offline"]
Result = Literal["ok", "fixed", "issue", "na"]
ActionKind = Literal["replace", "calibrate", "clean", "repair", "remove", "install"]
RemovalReason = Literal["faulty", "calibration", "retired", "other"]
Severity = Literal["low", "medium", "high"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionIn(In):
    status: Condition | None = None
    notes: Long | None = None


class ChecklistRowIn(In):
    # A template item's id (made by W10's editor) or, for the technician's own, a device-made one
    item_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    result: Result | None = None
    note: Line | None = None
    ad_hoc: bool = False
    label: Short | None = None  # only for an ad-hoc item


class CalibrationData(In):
    method: Literal["field_check", "field_adjust"] = "field_check"
    reference_instrument: ReferenceInstrument | None = None
    readings: Annotated[list[Reading], Field(max_length=50)] = []
    result: Literal["pass", "adjusted", "fail"]


class SensorActionIn(In):
    id: Id
    action: ActionKind
    parameter: Annotated[str, StringConstraints(max_length=40)] | None = None
    sensor_model_id: Id | None = None
    old_serial: Annotated[str, StringConstraints(max_length=80)] | None = None
    new_serial: Annotated[str, StringConstraints(max_length=80)] | None = None
    removal_reason: RemovalReason | None = None
    calibration: CalibrationData | None = None
    note: Line | None = None


class WorkConfigVersionIn(In):
    id: Id
    files: Annotated[list[Id], Field(max_length=20)]
    notes: Line | None = None


class PartIn(In):
    id: Id
    description: Short
    quantity: Annotated[int, Field(ge=1, le=999)] = 1


class IssueIn(In):
    id: Id
    description: Line
    severity: Severity = "medium"


class DownloadedIn(In):
    done: bool = False
    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None


class WorkIn(In):
    """The record whole, with the version the editor was looking at."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    base_version: Annotated[int, Field(ge=0)]
    device_id: Annotated[str, StringConstraints(max_length=64)] | None = None
    condition_on_arrival: ConditionIn | None = None
    checklist: Annotated[list[ChecklistRowIn], Field(max_length=200)] = []
    sensor_actions: list[SensorActionIn] = []
    config_versions: list[WorkConfigVersionIn] = []
    parts_used: list[PartIn] = []
    issues_found: list[IssueIn] = []
    data_downloaded: DownloadedIn | None = None
    condition_on_departure: ConditionIn | None = None
    notes: Long | None = None

    def record(self) -> dict[str, Any]:
        """What `domain/visits/work.clean_record` takes: plain data, `from` as `from`."""
        body: dict[str, Any] = _plain(
            self.model_dump(by_alias=True, exclude={"base_version", "device_id"})
        )
        return body


class ChecklistRowOut(BaseModel):
    item_id: str
    label: str
    group: str | None
    result: Result | None
    note: str | None
    ad_hoc: bool


class ConditionOut(BaseModel):
    status: Condition | None
    notes: str | None


class DownloadedOut(BaseModel):
    done: bool
    from_: datetime | None = Field(default=None, serialization_alias="from")
    to: datetime | None = None


class WorkOut(BaseModel):
    """A station's work record as staff see it. Clients never get one (rule 6)."""

    model_config = ConfigDict(populate_by_name=True)

    version: int
    updated_by: str | None
    updated_at: datetime | None
    device_id: str | None
    condition_on_arrival: ConditionOut | None
    checklist: list[ChecklistRowOut]
    sensor_actions: list[dict[str, Any]]
    config_versions: list[dict[str, Any]]
    parts_used: list[dict[str, Any]]
    issues_found: list[dict[str, Any]]
    data_downloaded: DownloadedOut | None
    condition_on_departure: ConditionOut | None
    notes: str | None

    @classmethod
    def of(cls, work: dict[str, Any]) -> WorkOut:
        downloaded = work.get("data_downloaded")
        return cls(
            version=work["version"], updated_by=work.get("updated_by"),
            updated_at=work.get("updated_at"), device_id=work.get("device_id"),
            condition_on_arrival=work.get("condition_on_arrival"),
            checklist=work["checklist"], sensor_actions=work["sensor_actions"],
            config_versions=work["config_versions"], parts_used=work["parts_used"],
            issues_found=work["issues_found"],
            data_downloaded=(
                DownloadedOut(done=downloaded["done"], from_=downloaded["from"],
                              to=downloaded["to"]) if downloaded else None
            ),
            condition_on_departure=work.get("condition_on_departure"), notes=work.get("notes"),
        )


def _plain(value: Any) -> Any:
    """MongoDB stores datetimes but not dates: a calendar date (a certificate's due day) is kept
    as its ISO text."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    return value
