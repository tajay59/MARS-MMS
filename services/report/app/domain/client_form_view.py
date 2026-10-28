"""What the client form template shows, built from operations' facts (PRD CRP-3; W18-10). No I/O:
pictures arrive as data URIs the job prepared.

Times are written in the zone of the first station that has one, with the zone's abbreviation
(RPT-9). The organization's name heads the page; there is no per-organization template (the one
brand is MARS-MMS's, W4-12).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from app.domain.client_form import short
from app.domain.visit_view import Pictures, local


def build(
    report: Mapping[str, Any], facts: Mapping[str, Any], pictures: Pictures, *,
    generated_at: datetime,
) -> dict[str, Any]:
    stations = list(facts["stations"])
    zone = next((s["time_zone"] for s in stations if s.get("time_zone")), None)
    notes = {o["station_id"]: o["text"] for o in facts["observations"]}
    covered = [
        {"code": s["code"], "name": s["name"], "country": s.get("country"),
         "observation": notes.get(s["station_id"], "")}
        for s in stations
    ]
    return {
        "number": report["number"], "version": report["version"],
        "org_name": facts.get("org_name"), "title": facts["title"],
        "report_date": f"{(d := date.fromisoformat(facts['report_date'])).day:02d} {d:%b %Y}",
        "request_ref": facts["request"]["ref"], "request_title": facts["request"]["title"],
        "submitted_by": facts["submitted_by_name"],
        "submitted": local(facts["submitted_at"], zone),
        "generated": local(generated_at, zone),
        "stations": covered, "summary": facts["summary"],
        "data_quality_notes": facts["data_quality_notes"],
        "images": [
            {"name": i["name"], "uri": pictures.get(i["media_id"])} for i in facts["images"]
        ],
        "hash": short(report.get("content_hash")),
    }
