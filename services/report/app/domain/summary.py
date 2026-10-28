"""Summary reports (PRD SUM-1 to SUM-3, CAL-4; TRD 3.4, 11.1; decisions W19-8 to W19-10).

A summary is a pure function of the read model and its parameters: the repository fetches the
rows, `build` turns them into a `Doc` of tables, the job writes it as CSV (the main table) or
draws it as a PDF. A summary has no report number, version or signature, and it is not found by
`/reports/verify`; its footer says who made it and when. No I/O here (rule 7).

Built: ten of the eleven types. Technician workload needs staff names, which the read model
does not hold, and the charts (headless Chromium) follow with it.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from mms_common.errors import ValidationFailed

TEMPLATE_VERSION = "summary-1"
MAX_ROWS = 20_000  # a summary this long is not a summary: ask for a narrower one
MAX_STATIONS = 200


class Kind(StrEnum):
    STATION_HISTORY = "station_history"
    CLIENT_ACTIVITY = "client_activity"
    REQUEST_TURNAROUND = "request_turnaround"
    CALIBRATION_DUE = "calibration_due"
    NETWORK_STATUS = "network_status"
    MONTHLY_SUMMARY = "monthly_summary"
    ANNUAL_SUMMARY = "annual_summary"
    STATION_ASSET = "station_asset"
    SENSOR_RELIABILITY = "sensor_reliability"
    CONFIGURATION_HISTORY = "configuration_history"


@dataclass(frozen=True)
class TypeInfo:
    key: Kind
    title: str
    description: str
    clients: bool  # SUM-3: a client may run Station history and Client activity
    uses_period: bool = True


TYPES: dict[Kind, TypeInfo] = {t.key: t for t in (
    TypeInfo(Kind.STATION_HISTORY, "Station history",
             "What happened at each station: visits, requests and calibrations.", True),
    TypeInfo(Kind.CLIENT_ACTIVITY, "Client activity",
             "Requests, visits and how long they took, for the stations chosen.", True),
    TypeInfo(Kind.REQUEST_TURNAROUND, "Request turnaround",
             "How long each step takes, from submitted to closed.", False),
    TypeInfo(Kind.CALIBRATION_DUE, "Calibration due",
             "Units overdue or due soon, by station.", False, uses_period=False),
    TypeInfo(Kind.NETWORK_STATUS, "Network status",
             "Every station: status, last visit, open requests and overdue calibrations.",
             False, uses_period=False),
    TypeInfo(Kind.MONTHLY_SUMMARY, "Monthly summary",
             "Requests and visits in the period, by category and by country.", False),
    TypeInfo(Kind.ANNUAL_SUMMARY, "Annual summary",
             "Requests, visits and calibrations for each month of the period.", False),
    TypeInfo(Kind.STATION_ASSET, "Station asset",
             "What is installed at each station now: sensors, serials and calibration dates.",
             True, uses_period=False),
    TypeInfo(Kind.SENSOR_RELIABILITY, "Sensor reliability",
             "Installs, removals, failed calibrations and time in service for each sensor model.",
             False),
    TypeInfo(Kind.CONFIGURATION_HISTORY, "Configuration history",
             "The configuration versions saved for each station, and the visit behind each.",
             False),
)}


def allowed(kind: Kind, *, client: bool) -> bool:
    return TYPES[kind].clients or not client


@dataclass(frozen=True)
class Period:
    from_date: date
    to_date: date
    start: datetime  # UTC, inclusive: 00:00 of from_date in the report's zone
    end: datetime  # UTC, exclusive: 00:00 after to_date
    zone: str


def period(from_date: date, to_date: date, zone: str, max_days: int) -> Period:
    """The days chosen as a window of UTC times. A month starts at 00:00 in `zone` (W19-10)."""
    if to_date < from_date:
        raise ValidationFailed("The end date is before the start date", code="invalid_period")
    if (to_date - from_date).days + 1 > max_days:
        raise ValidationFailed(
            f"Choose a period of at most {max_days} days", code="invalid_period")
    tz = ZoneInfo(zone)
    start = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return Period(from_date, to_date, start, end, zone)


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[list[Any]]
    right: tuple[int, ...] = ()  # columns drawn right-aligned (numbers)


@dataclass
class Doc:
    kind: Kind
    title: str
    kpis: list[tuple[str, str]] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def main(self) -> Table:
        """The table that CSV exports: the first (SUM-2)."""
        return self.tables[0]


def days_between(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    if b.tzinfo is None:
        b = b.replace(tzinfo=UTC)
    return round((b - a).total_seconds() / 86400, 1)


def nearest_rank(values: list[float], percent: int) -> float | None:
    """The `percent`th percentile by nearest rank (the 90th of ten is the ninth)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-percent * len(ordered) // 100))  # ceiling
    return ordered[rank - 1]


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _number(value: float | None, unit: str = "") -> str:
    return "none" if value is None else f"{value:g}{unit}"


def _codes(ids: Iterable[str], stations: Mapping[str, Mapping[str, Any]]) -> str:
    return ", ".join(stations[i]["code"] for i in ids if i in stations)


# --- the types --------------------------------------------------------------------------------


def station_history(data: Mapping[str, Any]) -> Doc:
    stations = data["stations"]
    rows: list[list[Any]] = []
    for v in data["visits"]:
        rows.append([v["ended_at"], _codes(v["station_ids"], stations), "Visit", v.get("ref"),
                     "Request " + data["request_refs"].get(v["request_id"], "")])
    for r in data["requests"]:
        rows.append([r["submitted_at"], _codes(r["station_ids"], stations), "Request", r["ref"],
                     f"{r['category']}, {r['priority']} priority, now {r['status']}"])
    for c in data["calibrations"]:
        serial = data["serials"].get(c["sensor_unit_id"], "")
        rows.append([c["at"], _codes([c["station_id"]], stations), "Calibration", serial,
                     f"{c['result']} ({c['method']})"])
    rows.sort(key=lambda row: (row[0], row[2]))
    return Doc(
        Kind.STATION_HISTORY, "Station history",
        kpis=[("Visits", str(len(data["visits"]))), ("Requests", str(len(data["requests"]))),
              ("Calibrations", str(len(data["calibrations"])))],
        tables=[Table("Events", ["When", "Station", "What", "Reference", "Detail"], rows)],
    )


def client_activity(data: Mapping[str, Any]) -> Doc:
    visits = Counter(v["request_id"] for v in data["visits"])
    rows: list[list[Any]] = []
    closed_days: list[float] = []
    for r in sorted(data["requests"], key=lambda x: x["submitted_at"]):
        took = days_between(r["submitted_at"], r.get("closed_at"))
        if took is not None and r["status"] == "closed":
            closed_days.append(took)
        rows.append([r["ref"], r["category"], r["priority"], r["status"], r["submitted_at"],
                     r.get("closed_at"), visits.get(r["_id"], 0), r.get("reopen_count") or 0])
    sent_back = sum(1 for r in data["requests"] if (r.get("reopen_count") or 0) > 0)
    return Doc(
        Kind.CLIENT_ACTIVITY, "Client activity",
        kpis=[("Requests", str(len(rows))), ("Closed", str(len(closed_days))),
              ("Sent back by the client", str(sent_back)),
              ("Median days to close", _number(median(closed_days)))],
        tables=[Table("Requests", ["Request", "Category", "Priority", "Status", "Submitted",
                                   "Closed", "Visits", "Sent back"], rows, right=(6, 7))],
    )


def request_turnaround(data: Mapping[str, Any]) -> Doc:
    rows: list[list[Any]] = []
    by_category: dict[str, list[float]] = defaultdict(list)
    totals: list[float] = []
    for r in sorted(data["requests"], key=lambda x: x["closed_at"]):
        steps = [days_between(r["submitted_at"], r.get(key))
                 for key in ("approved_at", "assigned_at", "first_visit_at", "closed_at")]
        if steps[3] is not None:
            totals.append(steps[3])
            by_category[r["category"]].append(steps[3])
        rows.append([r["ref"], r["category"], r["submitted_at"], *steps,
                     r.get("reopen_count") or 0])
    summary = [[c, len(v), median(v), nearest_rank(v, 90)] for c, v in sorted(by_category.items())]
    return Doc(
        Kind.REQUEST_TURNAROUND, "Request turnaround",
        kpis=[("Requests closed", str(len(rows))),
              ("Median, submitted to closed", _number(median(totals), " days")),
              ("90th percentile", _number(nearest_rank(totals, 90), " days"))],
        tables=[
            Table("Closed requests, days from submission",
                  ["Request", "Category", "Submitted", "To approved", "To assigned",
                   "To first visit", "To closed", "Sent back"], rows, right=(3, 4, 5, 6, 7)),
            Table("By category", ["Category", "Closed", "Median days", "90th percentile"],
                  summary, right=(1, 2, 3)),
        ],
        notes=["Requests that were denied or cancelled are not counted. A request the client "
               "sent back counts from its first submission to its final close."],
    )


def calibration_due(data: Mapping[str, Any]) -> Doc:
    now: datetime = data["now"]
    stations = data["stations"]
    rows: list[list[Any]] = []
    overdue = soon = 0
    for u in sorted(data["units"], key=lambda x: x["due_at"]):
        left = days_between(now, u["due_at"])
        late = u["due_at"] < now
        overdue, soon = overdue + late, soon + (not late)
        station = stations.get(u["station_id"], {})
        rows.append([station.get("code", ""), station.get("name", ""), u["serial"], u["due_at"],
                     left, "Overdue" if late else "Due soon"])
    return Doc(
        Kind.CALIBRATION_DUE, "Calibration due",
        kpis=[("Overdue", str(overdue)), (f"Due in {data['due_in_days']} days", str(soon))],
        tables=[Table("Units", ["Station", "Name", "Serial", "Due", "Days left", "State"],
                      rows, right=(4,))],
        notes=["Days left is negative when the calibration is overdue."],
    )


def network_status(data: Mapping[str, Any]) -> Doc:
    rows: list[list[Any]] = []
    counts: Counter[str] = Counter()
    for s in sorted(data["stations"].values(), key=lambda x: (x["country"], x["code"])):
        counts[s["status"]] += 1
        rows.append([s["code"], s["name"], s["country"], s["status"],
                     data["last_visit"].get(s["_id"]), data["open_requests"].get(s["_id"], 0),
                     data["overdue_units"].get(s["_id"], 0)])
    return Doc(
        Kind.NETWORK_STATUS, "Network status",
        kpis=[("Stations", str(len(rows))), ("Operational", str(counts["operational"])),
              ("Degraded or offline", str(counts["degraded"] + counts["offline"]))],
        tables=[Table("Stations", ["Code", "Name", "Country", "Status", "Last visit",
                                   "Open requests", "Overdue calibrations"], rows,
                      right=(5, 6))],
    )


def monthly_summary(data: Mapping[str, Any]) -> Doc:
    stations = data["stations"]

    def country(ids: list[str]) -> str:
        return next((stations[i]["country"] for i in ids if i in stations), "Unknown")

    categories: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    countries: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in data["submitted"]:
        categories[r["category"]][0] += 1
        countries[country(r["station_ids"])][0] += 1
    for r in data["closed"]:
        categories[r["category"]][1] += 1
        countries[country(r["station_ids"])][1] += 1
        categories[r["category"]][2] += 1 if (r.get("reopen_count") or 0) > 0 else 0
    for v in data["visits"]:
        countries[country(v["station_ids"])][2] += 1
    return Doc(
        Kind.MONTHLY_SUMMARY, "Monthly summary",
        kpis=[("Requests submitted", str(len(data["submitted"]))),
              ("Requests closed", str(len(data["closed"]))),
              ("Visits ended", str(len(data["visits"])))],
        tables=[
            Table("By category", ["Category", "Submitted", "Closed", "Sent back"],
                  [[c, *v] for c, v in sorted(categories.items())], right=(1, 2, 3)),
            Table("By country", ["Country", "Submitted", "Closed", "Visits ended"],
                  [[c, *v] for c, v in sorted(countries.items())], right=(1, 2, 3)),
        ],
    )


def month_label(moment: datetime, zone: str) -> str:
    return moment.astimezone(ZoneInfo(zone)).strftime("%Y-%m")


def annual_summary(data: Mapping[str, Any]) -> Doc:
    zone = data["zone"]
    months: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for key, idx in (("submitted", 0), ("closed", 1), ("visits", 2), ("calibrations", 3)):
        for row in data[key]:
            stamp = row.get({"submitted": "submitted_at", "closed": "closed_at",
                             "visits": "ended_at", "calibrations": "at"}[key])
            if stamp is not None:
                months[month_label(stamp, zone)][idx] += 1
    rows: list[list[Any]] = [[m, *v] for m, v in sorted(months.items())]
    return Doc(
        Kind.ANNUAL_SUMMARY, "Annual summary",
        kpis=[("Requests submitted", str(sum(r[1] for r in rows))),
              ("Requests closed", str(sum(r[2] for r in rows))),
              ("Visits ended", str(sum(r[3] for r in rows))),
              ("Calibrations", str(sum(r[4] for r in rows)))],
        tables=[Table("By month", ["Month", "Requests submitted", "Requests closed",
                                   "Visits ended", "Calibrations recorded"], rows,
                      right=(1, 2, 3, 4))],
    )


def station_asset(data: Mapping[str, Any]) -> Doc:
    stations, units, models = data["stations"], data["units"], data["models"]
    last, now = data["last_cal"], data["now"]

    def where(i: Mapping[str, Any]) -> tuple[str, str, str]:
        return (stations.get(i["station_id"], {}).get("code", ""), i.get("parameter") or "",
                i.get("serial", ""))

    rows: list[list[Any]] = []
    overdue = 0
    for i in sorted(data["installs"], key=where):
        station = stations.get(i["station_id"], {})
        model = models.get(i.get("model_id"))
        due = units.get(i["unit_id"], {}).get("due_at")
        overdue += bool(due and due < now)
        rows.append([station.get("code", ""), station.get("name", ""), i.get("parameter") or "",
                     f"{model['manufacturer']} {model['model']}" if model else "",
                     i.get("serial", ""), i.get("installed_at"),
                     last.get(i["unit_id"], {}).get("at"), due])
    return Doc(
        Kind.STATION_ASSET, "Station asset",
        kpis=[("Stations", str(len({i["station_id"] for i in data["installs"]}))),
              ("Sensors installed", str(len(rows))), ("Calibrations overdue", str(overdue))],
        tables=[Table("Installed sensors", ["Station", "Name", "Parameter", "Model", "Serial",
                                            "Installed", "Last calibrated", "Next due"], rows)],
    )


def sensor_reliability(data: Mapping[str, Any]) -> Doc:
    models, units = data["models"], data["units"]
    table: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"installs": 0, "removals": 0, "failed": 0, "days": [], "now": 0})
    for i in data["installed"]:
        table[i.get("model_id", "")]["installs"] += 1
    for i in data["removed"]:
        row = table[i.get("model_id", "")]
        row["removals"] += 1
        took = days_between(i.get("installed_at"), i.get("removed_at"))
        if took is not None:
            row["days"].append(took)
    for c in data["failed"]:
        table[units.get(c["sensor_unit_id"], {}).get("model_id", "")]["failed"] += 1
    for i in data["open"]:
        table[i.get("model_id", "")]["now"] += 1
    rows: list[list[Any]] = []
    for model_id, t in table.items():
        model = models.get(model_id)
        name = f"{model['manufacturer']} {model['model']}" if model else "Unknown model"
        mean = round(sum(t["days"]) / len(t["days"]), 1) if t["days"] else None
        rows.append([name, model["kind"] if model else "", t["installs"], t["removals"],
                     t["failed"], mean, t["now"]])
    rows.sort(key=lambda r: (-r[4], r[0]))
    return Doc(
        Kind.SENSOR_RELIABILITY, "Sensor reliability",
        kpis=[("Models", str(len(rows))), ("Removals", str(sum(r[3] for r in rows))),
              ("Failed calibrations", str(sum(r[4] for r in rows)))],
        tables=[Table("By model", ["Model", "Kind", "Installed", "Removed", "Failed calibrations",
                                   "Mean days in service", "In service now"], rows,
                      right=(2, 3, 4, 5, 6))],
        notes=["Mean days in service counts sensors removed in the period only."],
    )


def configuration_history(data: Mapping[str, Any]) -> Doc:
    stations, visits = data["stations"], data["visit_refs"]
    rows = [[c["created_at"], stations.get(c["station_id"], {}).get("code", ""), c["number"],
             c["file_count"], visits.get(c.get("visit_id"), "")]
            for c in sorted(data["configs"], key=lambda x: x["created_at"])]
    return Doc(
        Kind.CONFIGURATION_HISTORY, "Configuration history",
        kpis=[("Versions saved", str(len(rows))),
              ("Stations changed", str(len({c["station_id"] for c in data["configs"]})))],
        tables=[Table("Versions", ["When", "Station", "Version", "Files", "Visit"], rows,
                      right=(2, 3))],
    )


BUILDERS: dict[Kind, Callable[[Mapping[str, Any]], Doc]] = {
    Kind.STATION_HISTORY: station_history,
    Kind.CLIENT_ACTIVITY: client_activity,
    Kind.REQUEST_TURNAROUND: request_turnaround,
    Kind.CALIBRATION_DUE: calibration_due,
    Kind.NETWORK_STATUS: network_status,
    Kind.MONTHLY_SUMMARY: monthly_summary,
    Kind.ANNUAL_SUMMARY: annual_summary,
    Kind.STATION_ASSET: station_asset,
    Kind.SENSOR_RELIABILITY: sensor_reliability,
    Kind.CONFIGURATION_HISTORY: configuration_history,
}


def build(kind: Kind, data: Mapping[str, Any]) -> Doc:
    return BUILDERS[kind](data)


# --- how a Doc is shown ---------------------------------------------------------------------


def cell_text(value: Any, zone: str) -> str:
    """A cell for the PDF: times in the report's zone, numbers as they are, empty for none."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        local = (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(ZoneInfo(zone))
        return local.strftime("%Y-%m-%d %H:%M") if local.time() != time.min else local.strftime(
            "%Y-%m-%d")
    return str(value)


def pdf_view(doc: Doc, *, subtitle: str, filters: str, zone: str, generated_at: datetime,
             generated_by: str) -> dict[str, Any]:
    return {
        "title": doc.title, "subtitle": subtitle, "filters": filters, "zone": zone,
        "kpis": [{"label": k, "value": v} for k, v in doc.kpis],
        "tables": [
            {"title": t.title, "columns": t.columns, "right": list(t.right),
             "rows": [[cell_text(c, zone) for c in row] for row in t.rows]}
            for t in doc.tables
        ],
        "notes": doc.notes,
        "generated": cell_text(generated_at.replace(second=0, microsecond=0), zone),
        "generated_by": generated_by,
    }


def file_name(kind: Kind, p: Period | None, fmt: str) -> str:
    """The name a download gets: the report and its period, never a person or a station."""
    dated = p is not None and TYPES[kind].uses_period
    span = f"_{p.from_date.isoformat()}_{p.to_date.isoformat()}" if dated and p else ""
    return f"{kind.value.replace('_', '-')}{span}.{fmt}"
