"""The station import (PRD STN-8, TRD §3.2 `POST /stations/import`). No I/O here.

Two tables: **stations** (one row per station) and, optionally, **sensors** (one row per
installed unit). They come as one XLSX workbook with sheets named `Stations` and `Sensors`,
or as CSV files. Headers are matched ignoring case, spaces and underscores, with the aliases
below. Every problem is reported with the spreadsheet's row number (the header is row 1);
valid rows are imported and invalid ones skipped (IP risk "Station data is poor").

The organization is matched by name to an existing one: an admin creates missing
organizations first. A station code that already exists is skipped, so the import can be
run again after fixing rows. The country defaults to the organization's.

**The existing system's export** (decision W5-8, TRD T4) is a third format: a MongoDB export
of its `site` collection (`.json`, a JSON array or one document per line). Each *device* in a
site becomes a station: `name` the code, `longname` the name, `id` the external ID, `lat`,
`lon`, `timezone`, and `params[].param` the parameters. The site's `entity` is matched to an
organization's external ID (`python -m app.cli import-orgs` in auth brings them in first),
and a disabled site's devices are decommissioned. Nothing else is read. Rows are numbered from
1 in the order the devices appear in the file. A device whose ID is already on a station is
skipped.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from mms_common.errors import ValidationFailed

from app.domain.stations import places, sensors
from app.domain.stations import stations as rules

MAX_STATION_ROWS = 5000
MAX_SENSOR_ROWS = 20000

STATIONS = "Stations"
SENSORS = "Sensors"

# Column -> accepted headers (already normalized: lower case, no spaces or underscores).
STATION_COLUMNS: dict[str, tuple[str, ...]] = {
    "code": ("code", "stationcode", "stationid"),
    "name": ("name", "stationname"),
    "external_id": ("externalid", "deviceid"),
    "organization": ("organization", "organisation", "org", "owner", "client"),
    "organization_external_id": ("organizationexternalid", "orgexternalid", "entity"),
    "country": ("country", "countrycode"),
    "time_zone": ("timezone", "tz"),
    "type": ("type", "stationtype"),
    "region": ("region", "parish", "district"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng", "long"),
    "elevation_m": ("elevationm", "elevation", "altitude", "altitudem"),
    "parameters": ("parameters", "parameter", "measured"),
    "status": ("status",),
    "install_date": ("installdate", "installed", "installedon"),
    "logger_model": ("loggermodel",),
    "logger_serial": ("loggerserial",),
    "logger_firmware": ("loggerfirmware", "firmware"),
    "comms_type": ("commstype", "communications", "comms"),
    "comms_provider": ("commsprovider", "provider"),
    "comms_identifier": ("commsidentifier", "simnumber", "imei"),
    "power_panel_w": ("powerpanelw", "panelw", "solarpanelw"),
    "power_battery_ah": ("powerbatteryah", "batteryah"),
    "power_controller": ("powercontroller", "controller"),
    "access_notes": ("accessnotes", "access", "notes"),
}
STATION_REQUIRED = ("code", "name", "latitude", "longitude")
# One of these names the owner: the organization's name, or its external ID (W5-8)
OWNER_COLUMNS = ("organization", "organization_external_id")
_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")

SENSOR_COLUMNS: dict[str, tuple[str, ...]] = {
    "station_code": ("stationcode", "station", "code"),
    "kind": ("kind", "component"),
    "manufacturer": ("manufacturer", "make", "brand"),
    "model": ("model",),
    "serial": ("serial", "serialnumber", "sn"),
    "parameter": ("parameter",),
    "installed_at": ("installedat", "installdate", "installed"),
    "last_calibrated_at": ("lastcalibratedat", "lastcalibrated", "lastcalibration"),
    "calibration_interval_days": ("calibrationintervaldays", "intervaldays"),
    "default_calibration_interval_days": ("defaultcalibrationintervaldays", "modelintervaldays"),
}
SENSOR_REQUIRED = ("station_code", "manufacturer", "model", "serial")

_SPLIT = re.compile(r"[,;/|\s]+")


@dataclass(frozen=True)
class RowError:
    sheet: str
    row: int
    column: str | None
    message: str


@dataclass
class StationRow:
    row: int
    fields: dict[str, Any]  # a station document's fields, without IDs and bookkeeping
    org: dict[str, Any]


@dataclass
class SensorRow:
    row: int
    station_code: str
    kind: str
    manufacturer: str
    model: str
    model_key: str
    serial: str
    parameter: str | None
    installed_at: datetime
    last_calibrated_at: datetime | None
    calibration_interval_days: int | None
    default_calibration_interval_days: int | None


@dataclass
class Plan:
    stations: list[StationRow] = field(default_factory=list)
    sensors: list[SensorRow] = field(default_factory=list)
    skipped: list[RowError] = field(default_factory=list)  # existing codes; not errors
    errors: list[RowError] = field(default_factory=list)
    warnings: list[RowError] = field(default_factory=list)
    station_rows: int = 0
    sensor_rows: int = 0


class SheetError(ValueError):
    """The file as a whole can't be read (not a CSV or XLSX, no header, too many rows)."""


# --- Reading files ---------------------------------------------------------------------------


Table = list[tuple[int, dict[str, Any]]]  # (spreadsheet row number, header -> cell)


def norm_header(header: Any) -> str:
    return re.sub(r"[\s_\-()]+", "", str(header or "")).lower()


def _table(rows: Iterable[Iterable[Any]]) -> Table:
    it = iter(rows)
    header: list[str] | None = None
    number = 0
    for raw in it:
        number += 1
        cells = list(raw)
        if any(c not in (None, "") for c in cells):
            header = [norm_header(c) for c in cells]
            break
    if header is None:
        return []
    table: Table = []
    for raw in it:
        number += 1
        cells = list(raw)
        if all(c is None or str(c).strip() == "" for c in cells):
            continue
        table.append((number, {h: cells[i] if i < len(cells) else None
                               for i, h in enumerate(header) if h}))
    return table


def read_csv(content: bytes) -> Table:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return _table(csv.reader(io.StringIO(text), dialect))


def read_xlsx(content: bytes) -> dict[str, Table]:
    """Sheet name (as `Stations` / `Sensors` when they match) -> table."""
    from openpyxl import load_workbook  # imported here: only the import needs it

    try:
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises many types for a bad file
        raise SheetError("The file is not a readable XLSX workbook") from exc
    tables: dict[str, Table] = {}
    try:
        for sheet in book.worksheets:
            known = {"stations": STATIONS, "sensors": SENSORS}
            name = known.get(norm_header(sheet.title), sheet.title)
            tables[name] = _table(sheet.iter_rows(values_only=True))
    finally:
        book.close()
    return tables


def _json_documents(content: bytes) -> list[Any]:
    try:
        text = content.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise SheetError("The file is not UTF-8 text") from exc
    try:
        if text.startswith("["):
            docs = json.loads(text)
        else:
            docs = [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise SheetError(f"The file is not JSON (line {exc.lineno})") from exc
    if not isinstance(docs, list):
        raise SheetError("Expected one JSON object per site")
    return docs


def read_sites(content: bytes) -> Table:
    """The existing system's `site` export as a stations table, one row per device (W5-8).
    Only the fields below are read; everything else in the documents is ignored."""
    table: Table = []
    for site in _json_documents(content):
        devices = site.get("devices") if isinstance(site, dict) else None
        if not isinstance(devices, list):
            continue
        status = "decommissioned" if site.get("enabled") is False else "operational"
        for device in devices:
            if not isinstance(device, dict):
                continue
            params = [
                p.get("param") or p.get("base") for p in device.get("params") or []
                if isinstance(p, dict)
            ]
            table.append((len(table) + 1, {
                "code": device.get("name"),
                "name": device.get("longname") or device.get("name"),
                "externalid": device.get("id"),
                "organizationexternalid": site.get("entity"),
                "timezone": device.get("timezone"),
                "latitude": device.get("lat"),
                "longitude": device.get("lon"),
                "parameters": ";".join(p for p in params if isinstance(p, str)),
                "status": status,
            }))
    if len(table) > MAX_STATION_ROWS:
        raise SheetError(f"Import at most {MAX_STATION_ROWS} stations at once")
    if not table:
        raise SheetError("No sites with devices in the file")
    return table


def read_file(filename: str, content: bytes) -> dict[str, Table]:
    lower = filename.lower()
    if lower.endswith(".json"):
        return {STATIONS: read_sites(content)}
    if lower.endswith(".xlsx"):
        tables = read_xlsx(content)
        if STATIONS not in tables and len(tables) >= 1:
            first = next(iter(tables))
            tables[STATIONS] = tables.pop(first)
        return tables
    if lower.endswith((".csv", ".txt")):
        return {STATIONS: read_csv(content)}
    raise SheetError("Upload an XLSX workbook, a CSV file or the site export (JSON)")


# --- Cell values -----------------------------------------------------------------------------


class _Bad(ValueError):
    pass


def _pick(row: Mapping[str, Any], columns: Mapping[str, tuple[str, ...]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column, names in columns.items():
        for name in names:
            if name in row and row[name] not in (None, ""):
                value = row[name]
                out[column] = value.strip() if isinstance(value, str) else value
                break
    return {k: v for k, v in out.items() if v != ""}


def _missing_columns(table: Table, columns: Mapping[str, tuple[str, ...]],
                     required: tuple[str, ...]) -> list[str]:
    if not table:
        return []
    headers = set().union(*(row.keys() for _, row in table))
    return [c for c in required if not headers & set(columns[c])]


def _text(value: Any, limit: int = 200) -> str:
    text = str(value).strip()
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))  # 12.0 from a spreadsheet number cell
    if len(text) > limit:
        raise _Bad(f"Use at most {limit} characters")
    return text


def _number(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError as exc:
        raise _Bad(f"{value!r} is not a number") from exc


def _whole(value: Any) -> int:
    number = _number(value)
    if not number.is_integer() or number <= 0:
        raise _Bad(f"{value!r} is not a whole number of days")
    return int(number)


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise _Bad(f"{value!r} is not a date: use YYYY-MM-DD") from exc


def local_midnight(day: date, time_zone: str) -> datetime:
    """A date in the station's time zone as a UTC instant (rule 8)."""
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(time_zone)).astimezone(UTC)


def _status(value: Any) -> str:
    text = str(value).strip().lower()
    try:
        return rules.Status(text).value
    except ValueError as exc:
        allowed = ", ".join(s.value for s in rules.Status)
        raise _Bad(f"{value!r} is not a status: use {allowed}") from exc


def _kind(value: Any) -> str:
    text = re.sub(r"[\s-]+", "_", str(value).strip().lower())
    try:
        return sensors.Kind(text).value
    except ValueError as exc:
        allowed = ", ".join(k.value for k in sensors.Kind)
        raise _Bad(f"{value!r} is not a kind: use {allowed}") from exc


def org_key(name: str) -> str:
    return " ".join(name.split()).casefold()


# --- Planning --------------------------------------------------------------------------------


def plan(
    station_table: Table,
    sensor_table: Table,
    *,
    orgs_by_key: Mapping[str, dict[str, Any]],
    existing_codes: Mapping[str, dict[str, Any]],
    models_by_key: Mapping[str, dict[str, Any]],
    units_by_model_serial: Mapping[tuple[str, str], dict[str, Any]],
    today: date,
    orgs_by_external: Mapping[str, dict[str, Any]] | None = None,
    existing_external_ids: Mapping[str, dict[str, Any]] | None = None,
) -> Plan:
    """Check every row. `orgs_by_key`: active organizations by `org_key(name)`;
    `existing_codes`: stations already in the system; `models_by_key` and
    `units_by_model_serial`: the inventory, to match sensors to what exists.
    `orgs_by_external` and `existing_external_ids`: the same by external ID (W5-8)."""
    orgs_by_external = orgs_by_external or {}
    existing_external_ids = existing_external_ids or {}
    if len(station_table) > MAX_STATION_ROWS or len(sensor_table) > MAX_SENSOR_ROWS:
        raise SheetError(
            f"Import at most {MAX_STATION_ROWS} stations and {MAX_SENSOR_ROWS} sensors at once"
        )
    result = Plan(station_rows=len(station_table), sensor_rows=len(sensor_table))
    for column in _missing_columns(station_table, STATION_COLUMNS, STATION_REQUIRED):
        result.errors.append(RowError(STATIONS, 1, column, f"No {column} column"))
    if station_table and len(_missing_columns(station_table, STATION_COLUMNS, OWNER_COLUMNS)) == 2:
        result.errors.append(RowError(STATIONS, 1, "organization", "No organization column"))
    for column in _missing_columns(sensor_table, SENSOR_COLUMNS, SENSOR_REQUIRED):
        result.errors.append(RowError(SENSORS, 1, column, f"No {column} column"))
    if result.errors:
        return result

    by_code: dict[str, StationRow] = {}
    bad_codes: dict[str, int] = {}
    by_external: dict[str, int] = {}
    for number, raw in station_table:
        row = _station_row(number, _pick(raw, STATION_COLUMNS), orgs_by_key, orgs_by_external,
                           result)
        if row is None:
            code = _pick(raw, STATION_COLUMNS).get("code")
            if code:
                bad_codes.setdefault(rules.normalize_code(str(code)), number)
            continue
        code = row.fields["code"]
        if code in by_code or code in bad_codes:
            first = by_code[code].row if code in by_code else bad_codes[code]
            result.errors.append(
                RowError(STATIONS, number, "code", f"Code {code} is also on row {first}")
            )
            continue
        if code in existing_codes:
            result.skipped.append(
                RowError(STATIONS, number, "code", f"Station {code} already exists")
            )
            continue
        external_id = row.fields.get("external_id")
        if external_id and external_id in by_external:
            result.errors.append(RowError(
                STATIONS, number, "external_id",
                f"External ID {external_id} is also on row {by_external[external_id]}",
            ))
            continue
        if external_id and external_id in existing_external_ids:
            already = existing_external_ids[external_id].get("code", "")
            result.skipped.append(RowError(
                STATIONS, number, "external_id",
                f"{external_id} was already imported as station {already}",
            ))
            continue
        if external_id:
            by_external[external_id] = number
        by_code[code] = row
        result.stations.append(row)

    occupied: dict[str, dict[str, int]] = {}  # station code -> parameter -> row
    seen_units: dict[tuple[str, str], int] = {}
    new_models: dict[str, tuple[str, int]] = {}  # model key -> (kind, first row)
    for number, raw in sensor_table:
        sensor = _sensor_row(number, _pick(raw, SENSOR_COLUMNS), result, today)
        if sensor is None:
            continue
        code = sensor.station_code
        station = by_code.get(code)
        existing = existing_codes.get(code)
        if station is None and existing is None:
            message = (
                f"Station {code} has errors on row {bad_codes[code]}" if code in bad_codes
                else f"No station {code} in this import or in the system"
            )
            result.errors.append(RowError(SENSORS, number, "station_code", message))
            continue
        if station is None:
            # Existing station: its inventory is managed in the app, not by re-importing.
            result.skipped.append(RowError(
                SENSORS, number, "station_code", f"Station {code} already exists; not changed"
            ))
            continue
        if not _sensor_fits(sensor, station, models_by_key, units_by_model_serial,
                            occupied.setdefault(code, {}), seen_units, new_models, result):
            continue
        result.sensors.append(sensor)
    return result


def _station_row(
    number: int,
    cells: dict[str, Any],
    orgs_by_key: Mapping[str, dict[str, Any]],
    orgs_by_external: Mapping[str, dict[str, Any]],
    result: Plan,
) -> StationRow | None:
    errors: list[RowError] = []

    def get(column: str, convert: Any = _text) -> Any:
        if column not in cells:
            if column in STATION_REQUIRED:
                errors.append(RowError(STATIONS, number, column, f"{column} is required"))
            return None
        try:
            return convert(cells[column])
        except _Bad as exc:
            errors.append(RowError(STATIONS, number, column, str(exc)))
            return None

    code = get("code")
    if code is not None:
        try:
            code = rules.check_code(code)
        except ValidationFailed as exc:
            errors.append(RowError(STATIONS, number, "code", str(exc)))
            code = None
    name = get("name", lambda v: _text(v, 120))
    org_name = get("organization")
    org_external = get("organization_external_id")
    org: dict[str, Any] | None = None
    if org_name:
        org = orgs_by_key.get(org_key(org_name))
        if org is None:
            errors.append(RowError(
                STATIONS, number, "organization",
                f"No active organization named {org_name!r}: create it first",
            ))
    elif org_external:
        org = orgs_by_external.get(org_external)
        if org is None:
            errors.append(RowError(
                STATIONS, number, "organization",
                f"No active organization with external ID {org_external}: import the "
                "organizations first",
            ))
    else:
        errors.append(RowError(STATIONS, number, "organization", "organization is required"))
    external_id = get("external_id", lambda v: _text(v, 64))
    if external_id is not None and not _EXTERNAL_ID.match(external_id):
        errors.append(RowError(
            STATIONS, number, "external_id", "Use letters, digits and . _ : - only (64 at most)"
        ))
    country_raw = get("country")
    country = places.country_code(country_raw) if country_raw else None
    if country_raw and country is None:
        errors.append(RowError(STATIONS, number, "country", f"{country_raw!r} is not a country"))
    elif country_raw is None and org is not None:
        country = org.get("country")  # the organization's, when the row gives none
    time_zone = get("time_zone")
    if time_zone is None and country is not None:
        time_zone = places.default_time_zone(country)
        if time_zone is None:
            errors.append(RowError(
                STATIONS, number, "time_zone",
                f"{country} has several time zones: give one, for example "
                f"{places.zones_by_country().get(country, ('UTC',))[0]}",
            ))
    elif time_zone is not None and not places.valid_time_zone(time_zone):
        errors.append(RowError(STATIONS, number, "time_zone", f"{time_zone!r} is not a time zone"))
        time_zone = None
    latitude = get("latitude", _number)
    longitude = get("longitude", _number)
    location = None
    if latitude is not None and longitude is not None:
        try:
            location = rules.point(latitude, longitude)
        except ValidationFailed as exc:
            errors.append(RowError(STATIONS, number, "latitude", str(exc)))
    parameters: list[str] = []
    raw_parameters = get("parameters")
    if raw_parameters:
        try:
            parameters = rules.check_parameters([p for p in _SPLIT.split(raw_parameters) if p])
        except ValidationFailed as exc:
            errors.append(RowError(STATIONS, number, "parameters", str(exc)))
    status = get("status", _status) or rules.Status.OPERATIONAL.value
    install_date = get("install_date", _date)
    elevation = get("elevation_m", _number)

    def group(prefix: str, names: tuple[str, ...], convert: Any = _text) -> dict[str, Any] | None:
        values = {n: get(f"{prefix}_{n}", convert) for n in names}
        return values if any(v is not None for v in values.values()) else None

    logger = group("logger", ("model", "serial", "firmware"))
    comms = group("comms", ("type", "provider", "identifier"))
    power: dict[str, Any] | None = {
        "panel_w": get("power_panel_w", _number),
        "battery_ah": get("power_battery_ah", _number),
        "controller": get("power_controller"),
    }
    if power is not None and all(v is None for v in power.values()):
        power = None
    type_ = get("type", lambda v: _text(v, 60))
    region = get("region")
    access_notes = get("access_notes", lambda v: _text(v, 2000))

    if errors:
        result.errors.extend(errors)
        return None
    assert org is not None and country is not None and time_zone is not None  # noqa: S101
    return StationRow(
        row=number,
        org=org,
        fields={
            "code": code, "name": name, "type": type_, "external_id": external_id,
            "owner_org_id": org["_id"], "owner_org_name": org["name"],
            "country": country, "time_zone": time_zone, "region": region,
            "location": location, "elevation_m": elevation, "parameters": parameters,
            "logger": logger, "comms": comms, "power": power,
            "install_date": install_date.isoformat() if install_date else None,
            "status": status, "access_notes": access_notes,
        },
    )


def _sensor_row(number: int, cells: dict[str, Any], result: Plan, today: date) -> SensorRow | None:
    errors: list[RowError] = []

    def get(column: str, convert: Any = _text) -> Any:
        if column not in cells:
            if column in SENSOR_REQUIRED:
                errors.append(RowError(SENSORS, number, column, f"{column} is required"))
            return None
        try:
            return convert(cells[column])
        except _Bad as exc:
            errors.append(RowError(SENSORS, number, column, str(exc)))
            return None

    code = get("station_code")
    kind = get("kind", _kind) or sensors.Kind.SENSOR.value
    manufacturer = get("manufacturer", lambda v: _text(v, 120))
    model = get("model", lambda v: _text(v, 120))
    serial = get("serial", lambda v: _text(v, 80))
    parameter = get("parameter")
    if parameter is not None:
        try:
            parameter = rules.check_parameters([parameter])[0]
        except ValidationFailed as exc:
            errors.append(RowError(SENSORS, number, "parameter", str(exc)))
    elif kind == sensors.Kind.SENSOR:
        errors.append(RowError(SENSORS, number, "parameter", "A sensor needs its parameter"))
    installed = get("installed_at", _date)
    calibrated = get("last_calibrated_at", _date)
    interval = get("calibration_interval_days", _whole)
    default = get("default_calibration_interval_days", _whole)
    for column, day in (("installed_at", installed), ("last_calibrated_at", calibrated)):
        if day is not None and day > today:
            errors.append(RowError(SENSORS, number, column, "The date is in the future"))
    if errors:
        result.errors.extend(errors)
        return None
    return SensorRow(
        row=number, station_code=rules.normalize_code(code), kind=kind,
        manufacturer=manufacturer, model=model, model_key=sensors.model_key(manufacturer, model),
        serial=sensors.normalize_serial(serial), parameter=parameter,
        # Converted to instants once the station's time zone is known (_sensor_fits).
        installed_at=datetime.combine(installed or today, time.min),
        last_calibrated_at=datetime.combine(calibrated, time.min) if calibrated else None,
        calibration_interval_days=interval, default_calibration_interval_days=default,
    )


def _sensor_fits(
    sensor: SensorRow,
    station: StationRow,
    models_by_key: Mapping[str, dict[str, Any]],
    units_by_model_serial: Mapping[tuple[str, str], dict[str, Any]],
    occupied: dict[str, int],
    seen_units: dict[tuple[str, str], int],
    new_models: dict[str, tuple[str, int]],
    result: Plan,
) -> bool:
    number = sensor.row
    tz = station.fields["time_zone"]
    sensor.installed_at = local_midnight(sensor.installed_at.date(), tz)
    if sensor.last_calibrated_at is not None:
        sensor.last_calibrated_at = local_midnight(sensor.last_calibrated_at.date(), tz)

    model = models_by_key.get(sensor.model_key)
    if model is not None and model["kind"] != sensor.kind:
        result.errors.append(RowError(
            SENSORS, number, "kind",
            f"{sensor.manufacturer} {sensor.model} is a {model['kind']} in the catalogue",
        ))
        return False
    if model is None:
        kind, first = new_models.setdefault(sensor.model_key, (sensor.kind, number))
        if kind != sensor.kind:
            result.errors.append(RowError(
                SENSORS, number, "kind",
                f"{sensor.manufacturer} {sensor.model} is a {kind} on row {first}",
            ))
            return False
    unit_key = (sensor.model_key, sensor.serial.casefold())
    if unit_key in seen_units:
        result.errors.append(RowError(
            SENSORS, number, "serial",
            f"Serial {sensor.serial} is also on row {seen_units[unit_key]}",
        ))
        return False
    if model is not None:
        unit = units_by_model_serial.get((model["_id"], sensor.serial))
        if unit is not None and unit["status"] != sensors.UnitStatus.IN_STOCK:
            result.errors.append(RowError(
                SENSORS, number, "serial",
                f"Unit {sensor.serial} exists and is {unit['status'].replace('_', ' ')}",
            ))
            return False
    if sensor.parameter is not None:
        if sensor.parameter in occupied:
            result.errors.append(RowError(
                SENSORS, number, "parameter",
                f"{sensor.parameter} at {sensor.station_code} is already on row "
                f"{occupied[sensor.parameter]}",
            ))
            return False
        if sensor.parameter not in station.fields["parameters"]:
            station.fields["parameters"].append(sensor.parameter)
            result.warnings.append(RowError(
                SENSORS, number, "parameter",
                f"{sensor.parameter} added to station {sensor.station_code}'s parameters",
            ))
        occupied[sensor.parameter] = number
    seen_units[unit_key] = number
    return True
