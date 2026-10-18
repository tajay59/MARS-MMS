"""Station rules (PRD STN-1, STN-2, ORG-2; BSD B5; TRD §5.2). No I/O here."""

from __future__ import annotations

import re
import secrets
from enum import StrEnum
from typing import Any

from mms_common.errors import ValidationFailed

from app.domain.stations import places


class Status(StrEnum):
    """STN-2. Staff set it; it is not a state machine."""

    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DECOMMISSIONED = "decommissioned"


# STN-1: the usual measured parameters. Others are allowed ("others configurable") as short
# upper-case codes, so a new sensor type needs no release.
COMMON_PARAMETERS = ("AT", "RH", "BP", "RAIN", "WS", "WD", "SR")
_PARAMETER = re.compile(r"^[A-Z][A-Z0-9_]{0,15}$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,31}$")

# Fields an edit may change. `owner_org_id` is not among them: stations never change owner
# (BSD B5). `qr_token` changes only through regeneration (QR-5, Phase 2 W7).
EDITABLE = (
    "code", "name", "type", "country", "time_zone", "region", "location", "elevation_m",
    "parameters", "logger", "comms", "power", "install_date", "status", "access_notes",
)


def normalize_code(code: str) -> str:
    return code.strip().upper()


def check_code(code: str) -> str:
    code = normalize_code(code)
    if not _CODE.match(code):
        raise ValidationFailed(
            "Use 2 to 32 letters, digits, dots, dashes or underscores", code="invalid_code",
            field="code",
        )
    return code


def normalize_parameter(value: str) -> str:
    return value.strip().upper()


def check_parameters(values: list[str]) -> list[str]:
    """Upper-cased, de-duplicated, in the order given."""
    found: list[str] = []
    for value in values:
        code = normalize_parameter(value)
        if not _PARAMETER.match(code):
            raise ValidationFailed(
                f"{value!r} is not a parameter code (for example AT, RH, RAIN)",
                code="invalid_parameter", field="parameters",
            )
        if code not in found:
            found.append(code)
    return found


def check_place(country: str, time_zone: str) -> None:
    if not places.valid_country(country):
        raise ValidationFailed(
            "Use an ISO 3166 country code, for example BB", code="invalid_country",
            field="country",
        )
    if not places.valid_time_zone(time_zone):
        raise ValidationFailed(
            "Use an IANA time zone, for example America/Barbados", code="invalid_time_zone",
            field="time_zone",
        )


def point(latitude: float, longitude: float) -> dict[str, Any]:
    """GeoJSON stores longitude first (TRD §5.2)."""
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValidationFailed("Latitude or longitude is out of range", code="invalid_location")
    return {"type": "Point", "coordinates": [longitude, latitude]}


def new_qr_token() -> str:
    """The unguessable token printed on the station's label (QR-1). 16 random bytes."""
    return secrets.token_urlsafe(16)


def changed_fields(before: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Only the fields whose value really changes."""
    return {k: v for k, v in changes.items() if before.get(k) != v}
