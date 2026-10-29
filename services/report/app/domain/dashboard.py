"""The dashboards' figures (PRD SUM-4 to SUM-6, CAL-4, CAL-6; W19-7). No I/O here (rule 7).

A dashboard is numbers from the read model, computed on request and kept for a minute. Lists
(upcoming visits, open requests) come from the operations pages that already show them, because
those carry names the read model does not. Two figures are not here at all: registrations
pending (auth) and visits waiting to sync (the phone's own IndexedDB).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

View = Literal["admin", "technician", "client"]

# The request statuses a dashboard calls open, in the order of the status table (DBD)
OPEN_STATUSES = ("submitted", "approved", "assigned", "scheduled", "in_progress", "client_review",
                 "reopened")
# Where a technician's own requests stand: someone is on them and they are not yet with the client
WORKING_STATUSES = ("assigned", "scheduled", "in_progress", "reopened")
STATION_STATUSES = ("operational", "degraded", "offline", "decommissioned")
DUE_WITHIN_DAYS = 30
LIST_LIMIT = 5

# Which view each role may ask for. A Viewer sees the admin view, read only (PRD §2.3).
ALLOWED: dict[str, tuple[View, ...]] = {
    "admin": ("admin", "technician"),
    "viewer": ("admin",),
    "technician": ("technician",),
    "client": ("client",),
}
DEFAULT_VIEW: dict[str, View] = {
    "admin": "admin", "viewer": "admin", "technician": "technician", "client": "client",
}


def role_of(roles: Iterable[str]) -> str:
    """The role that decides the view, most senior first."""
    held = set(roles)
    for name in ("admin", "technician", "viewer", "client"):
        if name in held:
            return name
    return "client"


def view_for(roles: Iterable[str], asked: str | None) -> View | None:
    """The view to build, or None when this role may not ask for it."""
    role = role_of(roles)
    if asked is None:
        return DEFAULT_VIEW[role]
    return next((v for v in ALLOWED[role] if v == asked), None)


def by_status(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Open requests by status, every open status present even at zero."""
    counts = {r["_id"]: int(r["n"]) for r in rows}
    return [{"status": s, "count": counts.get(s, 0)} for s in OPEN_STATUSES]


def station_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {s: 0 for s in STATION_STATUSES}
    for r in rows:
        if r["_id"] in counts:
            counts[r["_id"]] = int(r["n"])
    return counts


def by_country(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Stations by country and status, the biggest country first."""
    table: dict[str, dict[str, int]] = defaultdict(lambda: {s: 0 for s in STATION_STATUSES})
    for r in rows:
        country, status = r["_id"]["country"], r["_id"]["status"]
        if status in STATION_STATUSES:
            table[country][status] += int(r["n"])
    out = [{"country": c, **counts, "total": sum(counts.values())} for c, counts in table.items()]
    return sorted(out, key=lambda x: (-x["total"], x["country"]))


def age_days(since: datetime | None, now: datetime) -> int:
    if since is None:
        return 0
    if since.tzinfo is None:
        since = since.replace(tzinfo=now.tzinfo)
    return max((now - since).days, 0)


def awaiting(report: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """A draft that is waiting to be finalized, with the words a row needs. The station codes
    and the lead's name are read from the facts the draft holds (they are blank until the facts
    have been read)."""
    facts = (report.get("content") or {}).get("facts") or {}
    lead = next((p["name"] for p in facts.get("staff", []) if p.get("lead")), None)
    return {
        "report_id": report["_id"], "number": report["number"], "version": report["version"],
        "visit_id": report["visit_id"], "request_id": report["request_id"],
        "station_codes": [s["code"] for s in facts.get("stations", []) if s.get("code")],
        "lead_name": lead, "age_days": age_days(report.get("ended_at"), now),
    }
