"""What a summary report draws (W19-11), as plain data.

One chart per report, chosen from the table the report already holds, so the chart and the table
always agree. `chart_for` is pure: `repo/charts.py` turns a `ChartSpec` into a picture. A report
with nothing to show (no rows, all zeros) has no chart, and Station asset has none by design.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.summary import Doc, Kind

MAX_BARS = 12  # more than this does not fit a page: the rest is named in the chart's note
MAX_MONTHS = 36  # the longest period is 1096 days


@dataclass(frozen=True)
class Series:
    name: str
    values: list[float]


@dataclass(frozen=True)
class ChartSpec:
    title: str
    categories: list[str]
    series: list[Series]
    horizontal: bool = False
    note: str | None = None
    # Spoken for a screen reader and printed under the picture: the figures in words
    alt: str = field(default="", compare=False)

    def to_view(self) -> dict[str, Any]:
        return {
            "title": self.title, "categories": self.categories, "horizontal": self.horizontal,
            "series": [{"name": s.name, "values": s.values} for s in self.series],
            "note": self.note, "alt": self.alt,
        }

    @classmethod
    def from_view(cls, view: Mapping[str, Any]) -> ChartSpec:
        return cls(
            title=view["title"], categories=list(view["categories"]),
            series=[Series(s["name"], list(s["values"])) for s in view["series"]],
            horizontal=bool(view.get("horizontal")), note=view.get("note"),
            alt=view.get("alt") or "",
        )


def _alt(title: str, categories: list[str], series: list[Series]) -> str:
    parts = []
    for i, category in enumerate(categories):
        figures = ", ".join(f"{s.name} {s.values[i]:g}" for s in series)
        parts.append(f"{category}: {figures}")
    return f"{title}. " + "; ".join(parts) + "."


def _spec(title: str, categories: list[str], series: list[Series], *, horizontal: bool = False,
          note: str | None = None) -> ChartSpec | None:
    """None when there is nothing to draw: no bars, or every bar is zero."""
    if not categories or not any(v for s in series for v in s.values):
        return None
    return ChartSpec(title, categories, series, horizontal, note,
                     _alt(title, categories, series))


def _counts(title: str, counts: Mapping[str, int], name: str, *,
            horizontal: bool = True) -> ChartSpec | None:
    """The biggest `MAX_BARS` counts, biggest first (ties by name)."""
    ranked = sorted(((k, v) for k, v in counts.items() if v), key=lambda kv: (-kv[1], kv[0]))
    shown = ranked[:MAX_BARS]
    note = (f"The {len(shown)} largest of {len(ranked)} are shown. "
            "The table has all of them.") if len(ranked) > len(shown) else None
    return _spec(title, [k for k, _ in shown], [Series(name, [float(v) for _, v in shown])],
                 horizontal=horizontal, note=note)


def _number(value: Any) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _month(moment: datetime, zone: str) -> str:
    return moment.astimezone(ZoneInfo(zone)).strftime("%Y-%m")


def _by_month(rows: Iterable[list[Any]], zone: str) -> ChartSpec | None:
    months = Counter(_month(row[0], zone) for row in rows if isinstance(row[0], datetime))
    kept = sorted(months)[-MAX_MONTHS:]
    return _spec("Events per month", kept, [Series("Events", [float(months[m]) for m in kept])])


def _grouped(doc: Doc, table: int, title: str, columns: list[int],
             limit: int = MAX_BARS) -> ChartSpec | None:
    t = doc.tables[table]
    rows = t.rows[:limit]
    note = (f"The first {len(rows)} of {len(t.rows)} are shown. The table has all of them."
            if len(t.rows) > len(rows) else None)
    return _spec(title, [str(r[0]) for r in rows],
                 [Series(t.columns[c], [_number(r[c]) for r in rows]) for c in columns],
                 note=note)


def _due_by_station(doc: Doc) -> ChartSpec | None:
    per: dict[str, Counter[str]] = {}
    for row in doc.main.rows:
        per.setdefault(str(row[0]) or "No station", Counter())[str(row[5])] += 1
    ranked = sorted(per.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    shown = ranked[:MAX_BARS]
    note = (f"The {len(shown)} stations with the most units are shown. "
            "The table has all of them.") if len(ranked) > len(shown) else None
    return _spec(
        "Units to calibrate, by station", [k for k, _ in shown],
        [Series(state, [float(c[state]) for _, c in shown]) for state in ("Overdue", "Due soon")],
        note=note)


def chart_for(doc: Doc, zone: str) -> ChartSpec | None:
    rows = doc.main.rows
    match doc.kind:
        case Kind.STATION_HISTORY:
            return _by_month(rows, zone)
        case Kind.CLIENT_ACTIVITY:
            return _counts("Requests by status", Counter(str(r[3]) for r in rows), "Requests")
        case Kind.REQUEST_TURNAROUND:
            return _grouped(doc, 1, "Days to close, by category", [2, 3])
        case Kind.CALIBRATION_DUE:
            return _due_by_station(doc)
        case Kind.NETWORK_STATUS:
            return _counts("Stations by status", Counter(str(r[3]) for r in rows), "Stations")
        case Kind.MONTHLY_SUMMARY:
            return _grouped(doc, 1, "By country", [1, 2, 3])
        case Kind.ANNUAL_SUMMARY:
            return _grouped(doc, 0, "By month", [1, 2, 3], MAX_MONTHS)
        case Kind.CONFIGURATION_HISTORY:
            return _counts("Versions saved, by station", Counter(str(r[1]) for r in rows),
                           "Versions")
        case Kind.TECHNICIAN_WORKLOAD:
            return _counts("Visits attended, by technician",
                           {str(r[0]): int(r[3]) for r in rows}, "Visits")
        case Kind.SENSOR_RELIABILITY:
            return _counts("Failed calibrations, by model",
                           {str(r[0]): int(r[4]) for r in rows}, "Failed calibrations")
        case _:
            return None
