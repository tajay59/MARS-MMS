"""Stations module request and response bodies. Requests forbid unknown fields.

Clients get the same shapes with staff-only fields emptied (STN-6): the QR token and the
configuration version on a station; review flags and notes on a unit.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from mms_common.auth import User
from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.stations import sensors as unit_rules
from app.domain.stations import stations as station_rules

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=32)]
# A station's ID in the system its data was imported from, for search and matching (W5-8)
ExternalId = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._:\-]{1,64}$")
]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
TimeZone = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Parameter = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=station_rules.PARAMETER_MAX_LENGTH,
)]
StationStatus = Literal["operational", "degraded", "offline", "decommissioned"]
Kind = Literal["sensor", "logger", "modem", "battery", "solar_panel", "other"]
UnitStatus = Literal["in_stock", "installed", "in_repair", "retired"]
EditableUnitStatus = Literal["in_stock", "in_repair", "retired"]
Interval = Annotated[int, Field(ge=1, le=3650)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Positive = Annotated[float, Field(ge=0, le=1_000_000)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Stations --------------------------------------------------------------------------------


class Logger(In):
    model: ShortText | None = None
    serial: ShortText | None = None
    firmware: ShortText | None = None


class Comms(In):
    type: ShortText | None = None  # for example cellular, satellite, radio
    provider: ShortText | None = None
    identifier: ShortText | None = None  # SIM, IMEI or address


class Power(In):
    panel_w: Positive | None = None
    battery_ah: Positive | None = None
    controller: ShortText | None = None


class StationFields(In):
    name: Text | None = None
    external_id: ExternalId | None = None
    type: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None
    country: Country | None = None
    time_zone: TimeZone | None = None
    region: ShortText | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    elevation_m: Annotated[float, Field(ge=-500, le=9000)] | None = None
    parameters: Annotated[list[Parameter], Field(max_length=40)] | None = None
    logger: Logger | None = None
    comms: Comms | None = None
    power: Power | None = None
    install_date: date | None = None
    status: StationStatus | None = None
    access_notes: LongText | None = None

    @model_validator(mode="after")
    def _both_coordinates(self) -> StationFields:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Give both latitude and longitude")
        return self


class StationIn(StationFields):
    code: Code
    name: Text
    owner_org_id: Id
    country: Country
    time_zone: TimeZone
    latitude: Latitude
    longitude: Longitude
    parameters: Annotated[list[Parameter], Field(max_length=40)] = []
    status: StationStatus = "operational"


class StationPatch(StationFields):
    """`owner_org_id` is not here: stations never change owner (BSD B5)."""

    version: int
    code: Code | None = None


class StationSummary(BaseModel):
    """A row of the station list (DBD "Stations list")."""

    id: str
    code: str
    name: str
    type: str | None
    status: str
    owner_org_id: str
    owner_org_name: str | None
    country: str
    time_zone: str
    region: str | None
    external_id: str | None = None
    parameters: list[str]
    latitude: float | None
    longitude: float | None
    next_calibration_due_at: datetime | None = None
    last_visit_at: datetime | None = None  # visits arrive in Phase 4

    @classmethod
    def of(cls, doc: dict[str, Any], due: datetime | None = None) -> StationSummary:
        lon, lat = (doc.get("location") or {}).get("coordinates") or (None, None)
        return cls(
            id=doc["_id"], code=doc["code"], name=doc["name"], type=doc.get("type"),
            status=doc["status"], owner_org_id=doc["owner_org_id"],
            owner_org_name=doc.get("owner_org_name"), country=doc["country"],
            time_zone=doc["time_zone"], region=doc.get("region"),
            external_id=doc.get("external_id"), parameters=list(doc.get("parameters", [])),
            latitude=lat, longitude=lon,
            next_calibration_due_at=due,
        )


class StationPage(BaseModel):
    items: list[StationSummary]
    total: int
    next_after: str | None


class OrgOption(BaseModel):
    id: str
    name: str


class StationFacets(BaseModel):
    countries: list[str]
    types: list[str]
    parameters: list[str]
    organizations: list[OrgOption]  # empty for clients: they see one organization


class Places(BaseModel):
    """The form's time zone choices: each country's IANA zones, from `tzdata` (W5-7)."""

    time_zones: dict[str, list[str]]


class ModelSummary(BaseModel):
    id: str
    kind: str
    manufacturer: str
    model: str

    @classmethod
    def of(cls, doc: dict[str, Any] | None, model_id: str) -> ModelSummary:
        if doc is None:
            return cls(id=model_id, kind="other", manufacturer="", model="")
        return cls(id=doc["_id"], kind=doc["kind"], manufacturer=doc["manufacturer"],
                   model=doc["model"])


class InstalledUnit(BaseModel):
    """STN-4: model, serial, install date, last calibration and calibration due."""

    unit_id: str
    serial: str
    parameter: str | None
    model: ModelSummary
    installed_at: datetime | None
    last_calibrated_at: datetime | None
    last_calibration_result: str | None
    calibration_due_at: datetime | None
    due_state: str | None
    flags: list[str]
    needs_review: bool


class StationDetail(StationSummary):
    elevation_m: float | None
    logger: dict[str, Any] | None
    comms: dict[str, Any] | None
    power: dict[str, Any] | None
    install_date: str | None
    access_notes: str | None
    photos: list[str]
    qr_token: str | None  # staff only
    current_config_version: int | None  # staff only (STN-6)
    installed: list[InstalledUnit]
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(
        cls, doc: dict[str, Any], viewer: User, installed: list[InstalledUnit],
        due: datetime | None,
    ) -> StationDetail:
        base = StationSummary.of(doc, due).model_dump()
        staff = not viewer.is_client
        return cls(
            **base, elevation_m=doc.get("elevation_m"), logger=doc.get("logger"),
            comms=doc.get("comms"), power=doc.get("power"),
            install_date=doc.get("install_date"), access_notes=doc.get("access_notes"),
            photos=list(doc.get("photos", [])),
            qr_token=doc.get("qr_token") if staff else None,
            current_config_version=doc.get("current_config_version") if staff else None,
            installed=installed, version=doc["version"], created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


class InstallationOut(BaseModel):
    id: str
    unit_id: str
    serial: str
    model: ModelSummary
    station_id: str
    station_code: str | None = None
    parameter: str | None
    installed_at: datetime
    removed_at: datetime | None
    removal_reason: str | None
    installed_visit_id: str | None
    removed_visit_id: str | None


# --- Sensor models ---------------------------------------------------------------------------


class SensorModelIn(In):
    kind: Kind
    manufacturer: Text
    model: Text
    parameters: Annotated[list[Parameter], Field(max_length=20)] = []
    default_calibration_interval_days: Interval | None = None


class SensorModelPatch(In):
    version: int
    kind: Kind | None = None
    manufacturer: Text | None = None
    model: Text | None = None
    parameters: Annotated[list[Parameter], Field(max_length=20)] | None = None
    default_calibration_interval_days: Interval | None = None


class SensorModelOut(BaseModel):
    id: str
    kind: str
    manufacturer: str
    model: str
    parameters: list[str]
    default_calibration_interval_days: int | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, doc: dict[str, Any]) -> SensorModelOut:
        return cls(
            id=doc["_id"], kind=doc["kind"], manufacturer=doc["manufacturer"],
            model=doc["model"], parameters=list(doc.get("parameters", [])),
            default_calibration_interval_days=doc.get("default_calibration_interval_days"),
            version=doc["version"], created_at=doc["created_at"], updated_at=doc["updated_at"],
        )


class SensorModelList(BaseModel):
    items: list[SensorModelOut]


# --- Sensor units ----------------------------------------------------------------------------


class SensorUnitIn(In):
    model_id: Id
    serial: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    status: EditableUnitStatus = "in_stock"
    calibration_interval_days: Interval | None = None
    last_calibrated_at: datetime | None = None  # from paper records; later ones are recorded
    notes: LongText | None = None


class SensorUnitPatch(In):
    version: int
    model_id: Id | None = None
    serial: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
        | None
    ) = None
    status: EditableUnitStatus | None = None
    # Send null to go back to the model's default interval.
    calibration_interval_days: Interval | None = None
    needs_review: bool | None = None
    notes: LongText | None = None


class InstallIn(In):
    version: int
    station_id: Id
    parameter: Parameter | None = None
    at: datetime | None = None  # defaults to now


class RemoveIn(In):
    version: int
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    status: EditableUnitStatus = "in_stock"
    at: datetime | None = None


class StationRef(BaseModel):
    id: str
    code: str
    name: str


class SensorUnitOut(BaseModel):
    id: str
    serial: str
    status: str
    model: ModelSummary
    station: StationRef | None
    parameter: str | None
    calibration_interval_days: int | None  # the override
    effective_interval_days: int | None  # override or the model's default (CAL-3)
    last_calibrated_at: datetime | None
    last_calibration_result: str | None
    calibration_due_at: datetime | None
    due_state: str | None
    needs_review: bool
    flags: list[str]
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(
        cls, doc: dict[str, Any], model: dict[str, Any] | None,
        station: dict[str, Any] | None, now: datetime,
    ) -> SensorUnitOut:
        due = doc.get("calibration_due_at")
        state = unit_rules.due_state(due, now)
        return cls(
            id=doc["_id"], serial=doc["serial"], status=doc["status"],
            model=ModelSummary.of(model, doc["model_id"]),
            station=StationRef(id=station["_id"], code=station["code"], name=station["name"])
            if station else None,
            parameter=doc.get("current_parameter"),
            calibration_interval_days=doc.get("calibration_interval_days"),
            effective_interval_days=unit_rules.interval_days(doc, model),
            last_calibrated_at=doc.get("last_calibrated_at"),
            last_calibration_result=doc.get("last_calibration_result"),
            calibration_due_at=due, due_state=state.value if state else None,
            needs_review=bool(doc.get("needs_review")), flags=list(doc.get("flags", [])),
            notes=doc.get("notes"), version=doc["version"], created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


class SensorUnitDetail(SensorUnitOut):
    installations: list[InstallationOut]


class SensorUnitPage(BaseModel):
    items: list[SensorUnitOut]
    next_after: str | None


# --- Calibrations ----------------------------------------------------------------------------


class ReferenceInstrument(In):
    model: ShortText | None = None
    serial: ShortText | None = None
    certificate_due: date | None = None


class Reading(In):
    reference: float | None = None
    before: float | None = None
    after: float | None = None
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None


class CalibrationIn(In):
    """A calibration recorded outside a visit (CAL-1); field checks come with visits."""

    sensor_unit_id: Id
    at: datetime
    method: Literal["field_check", "field_adjust", "lab"] = "lab"
    reference_instrument: ReferenceInstrument | None = None
    readings: Annotated[list[Reading], Field(max_length=50)] = []
    result: Literal["pass", "adjusted", "fail"]
    performed_by: ShortText | None = None  # defaults to the person recording it
    notes: LongText | None = None
    certificate_media_id: Id | None = None  # the certificate PDF, uploaded for this unit


class CalibrationOut(BaseModel):
    id: str
    sensor_unit_id: str
    station_id: str | None
    visit_id: str | None
    at: datetime
    method: str
    reference_instrument: dict[str, Any] | None
    readings: list[dict[str, Any]]
    result: str
    certificate_media_id: str | None
    performed_by: str | None
    notes: str | None
    created_at: datetime

    @classmethod
    def of(cls, doc: dict[str, Any]) -> CalibrationOut:
        return cls(
            id=doc["_id"], sensor_unit_id=doc["sensor_unit_id"], station_id=doc.get("station_id"),
            visit_id=doc.get("visit_id"), at=doc["at"], method=doc["method"],
            reference_instrument=doc.get("reference_instrument"),
            readings=list(doc.get("readings", [])), result=doc["result"],
            certificate_media_id=doc.get("certificate_media_id"),
            performed_by=doc.get("performed_by"), notes=doc.get("notes"),
            created_at=doc["created_at"],
        )


class CalibrationPage(BaseModel):
    items: list[CalibrationOut]
    next_after: str | None


class DueStation(BaseModel):
    id: str
    code: str
    name: str
    country: str
    owner_org_id: str
    owner_org_name: str | None


class DueUnit(BaseModel):
    """A row of the calibration-due list (CAL-4)."""

    unit_id: str
    serial: str
    status: str
    model: ModelSummary
    station: DueStation | None
    parameter: str | None
    last_calibrated_at: datetime | None
    calibration_due_at: datetime
    due_state: str


class DueList(BaseModel):
    items: list[DueUnit]
    within_days: int


# --- Import ----------------------------------------------------------------------------------


class ImportProblem(BaseModel):
    sheet: str
    row: int
    column: str | None
    message: str


class ImportReport(BaseModel):
    dry_run: bool
    station_rows: int
    sensor_rows: int
    stations_created: int
    sensors_created: int
    models_created: int
    skipped: list[ImportProblem]
    errors: list[ImportProblem]
    warnings: list[ImportProblem]
