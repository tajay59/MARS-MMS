"""Countries and time zones, from the IANA tz database (the `tzdata` package).

A station has an ISO 3166-1 alpha-2 country and an IANA time zone used for display only
(rule 8). `iso3166.tab` lists the countries and `zone.tab` the zones in each, so the form and
the import can suggest the zone of a one-zone country (PRD Q4).
"""

from __future__ import annotations

import zoneinfo
from functools import cache
from importlib import resources


def _rows(name: str) -> list[list[str]]:
    text = resources.files("tzdata.zoneinfo").joinpath(name).read_text(encoding="utf-8")
    return [line.split("\t") for line in text.splitlines() if line and not line.startswith("#")]


@cache
def countries() -> dict[str, str]:
    """ISO alpha-2 code → English name."""
    return {row[0]: row[1] for row in _rows("iso3166.tab")}


@cache
def zones_by_country() -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {}
    for row in _rows("zone.tab"):
        found.setdefault(row[0], []).append(row[2])
    # zone.tab lists a country's most populous zone first: the best example to offer.
    return {code: tuple(zones) for code, zones in found.items()}


@cache
def time_zones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def valid_country(code: str) -> bool:
    return code in countries()


def valid_time_zone(name: str) -> bool:
    return name in time_zones()


def default_time_zone(country: str) -> str | None:
    """The zone of a country that has exactly one, else None (the user chooses)."""
    zones = zones_by_country().get(country, ())
    return zones[0] if len(zones) == 1 else None


def _name_key(name: str) -> str:
    """tz's short names ("Trinidad & Tobago", "St Kitts & Nevis", "Britain (UK)") and the
    usual spellings compare equal."""
    text = name.lower().replace("&", " and ").replace(".", " ").replace(",", " ")
    words = ["st" if w == "saint" else w for w in text.split()]
    return " ".join(words)


@cache
def _codes_by_name() -> dict[str, str]:
    found: dict[str, str] = {}
    for code, name in countries().items():
        found[_name_key(name)] = code
        if "(" in name:  # "Britain (UK)": also "Britain" and "UK"
            short, _, inner = name.partition("(")
            found.setdefault(_name_key(short), code)
            found.setdefault(_name_key(inner.rstrip(")")), code)
    return found


def country_code(value: str) -> str | None:
    """An alpha-2 code from a code or an English name, as typed in a spreadsheet."""
    text = value.strip()
    if text.upper() in countries():
        return text.upper()
    return _codes_by_name().get(_name_key(text))
