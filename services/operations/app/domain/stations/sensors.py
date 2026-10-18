"""Sensor models, units, installations and calibrations (PRD SEN-1 to SEN-3, CAL-1 to CAL-4,
CAL-6; TRD §5.2). No I/O here.

A unit is installed and removed only through `install` and `remove`, which also write the
installation history (SEN-3). Its other status changes are direct edits.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from mms_common.errors import Conflict, ValidationFailed

# A record dated a little ahead of the server clock is a phone's clock, not a mistake.
CLOCK_SLACK = timedelta(minutes=5)
DUE_SOON_DAYS = 30  # CAL-4 default window


class Kind(StrEnum):
    SENSOR = "sensor"
    LOGGER = "logger"
    MODEM = "modem"
    BATTERY = "battery"
    SOLAR_PANEL = "solar_panel"
    OTHER = "other"


class UnitStatus(StrEnum):
    IN_STOCK = "in_stock"
    INSTALLED = "installed"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"


class Method(StrEnum):
    FIELD_CHECK = "field_check"
    FIELD_ADJUST = "field_adjust"
    LAB = "lab"


class Result(StrEnum):
    PASS = "pass"  # noqa: S105 - a calibration result, not a password
    ADJUSTED = "adjusted"
    FAIL = "fail"


class DueState(StrEnum):
    OVERDUE = "overdue"
    DUE_SOON = "due_soon"
    OK = "ok"


CALIBRATION_FAILED = "calibration_failed"  # CAL-6 flag


class UnitInstalled(Conflict):
    code, title = "unit_installed", "Remove the unit from its station first"


class UnitNotInStock(Conflict):
    code, title = "unit_not_in_stock", "Only a unit in stock can be installed"


class UnitNotInstalled(Conflict):
    code, title = "unit_not_installed", "This unit is not installed"


class ParameterTaken(Conflict):
    code, title = "parameter_taken", "Another unit already measures this parameter here"


class StationDecommissioned(Conflict):
    code, title = "station_decommissioned", "This station is decommissioned"


def model_key(manufacturer: str, model: str) -> str:
    """Models are unique by manufacturer and model, ignoring case and spacing."""
    return f"{' '.join(manufacturer.split()).casefold()}|{' '.join(model.split()).casefold()}"


def normalize_serial(serial: str) -> str:
    return serial.strip()


# --- Status edits ------------------------------------------------------------------------------

# Direct edits (PATCH). `installed` is reached only through `install`, and left only through
# `remove`. Retired can go back to stock to correct a mistake.
_EDITS: dict[UnitStatus, frozenset[UnitStatus]] = {
    UnitStatus.IN_STOCK: frozenset({UnitStatus.IN_REPAIR, UnitStatus.RETIRED}),
    UnitStatus.IN_REPAIR: frozenset({UnitStatus.IN_STOCK, UnitStatus.RETIRED}),
    UnitStatus.RETIRED: frozenset({UnitStatus.IN_STOCK}),
    UnitStatus.INSTALLED: frozenset(),
}

AFTER_REMOVAL = frozenset({UnitStatus.IN_STOCK, UnitStatus.IN_REPAIR, UnitStatus.RETIRED})


def check_status_edit(current: str, wanted: str) -> None:
    if current == wanted:
        return
    if UnitStatus(current) is UnitStatus.INSTALLED:
        raise UnitInstalled()
    if UnitStatus(wanted) not in _EDITS[UnitStatus(current)]:
        raise ValidationFailed(
            f"A unit can't go from {current} to {wanted} here", code="invalid_status",
            field="status",
        )


def check_install(
    unit: dict[str, Any],
    model: dict[str, Any],
    station: dict[str, Any],
    parameter: str | None,
    occupied: set[str],
) -> None:
    """`occupied`: parameters already measured by other units installed at the station."""
    if unit["status"] != UnitStatus.IN_STOCK:
        raise UnitInstalled() if unit["status"] == UnitStatus.INSTALLED else UnitNotInStock()
    if station["status"] == "decommissioned":
        raise StationDecommissioned()
    if model["kind"] == Kind.SENSOR and not parameter:
        raise ValidationFailed(
            "Choose the parameter this sensor measures", code="parameter_required",
            field="parameter",
        )
    if parameter is None:
        return
    if model.get("parameters") and parameter not in model["parameters"]:
        raise ValidationFailed(
            f"This model doesn't measure {parameter}", code="parameter_not_in_model",
            field="parameter",
        )
    if parameter not in station.get("parameters", []):
        raise ValidationFailed(
            f"The station doesn't list {parameter} among its parameters",
            code="parameter_not_at_station", field="parameter",
        )
    if parameter in occupied:
        raise ParameterTaken()


def check_when(at: datetime, now: datetime, *, not_before: datetime | None = None) -> None:
    if at > now + CLOCK_SLACK:
        raise ValidationFailed("The date is in the future", code="date_in_future", field="at")
    if not_before is not None and at < not_before:
        raise ValidationFailed(
            "The date is before the unit was installed", code="date_too_early", field="at"
        )


# --- Calibration (CAL-1, CAL-3, CAL-6) ---------------------------------------------------------


def interval_days(unit: dict[str, Any], model: dict[str, Any] | None) -> int | None:
    """The unit's override, else its model's default (CAL-3)."""
    override = unit.get("calibration_interval_days")
    if override is not None:
        return int(override)
    default = (model or {}).get("default_calibration_interval_days")
    return int(default) if default is not None else None


def due_at(last_calibrated_at: datetime | None, interval: int | None) -> datetime | None:
    if last_calibrated_at is None or not interval:
        return None
    return last_calibrated_at + timedelta(days=interval)


def due_state(
    due: datetime | None, now: datetime, within_days: int = DUE_SOON_DAYS
) -> DueState | None:
    if due is None:
        return None
    if due < now:
        return DueState.OVERDUE
    if due <= now + timedelta(days=within_days):
        return DueState.DUE_SOON
    return DueState.OK


def unit_after_calibration(
    unit: dict[str, Any], model: dict[str, Any] | None, at: datetime, result: str
) -> dict[str, Any]:
    """Changes to the unit for a new calibration record. A record older than the unit's last
    calibration only joins the history; it changes nothing on the unit."""
    last = unit.get("last_calibrated_at")
    if last is not None and at < last:
        return {}
    flags = [f for f in unit.get("flags", []) if f != CALIBRATION_FAILED]
    if result == Result.FAIL:
        flags.append(CALIBRATION_FAILED)
    return {
        "last_calibrated_at": at,
        "last_calibration_result": result,
        "calibration_due_at": due_at(at, interval_days(unit, model)),
        "flags": flags,
    }


def check_readings(readings: list[dict[str, Any]]) -> None:
    for reading in readings:
        if all(reading.get(k) is None for k in ("reference", "before", "after")):
            raise ValidationFailed(
                "Each reading needs a reference, before or after value", code="empty_reading",
                field="readings",
            )
