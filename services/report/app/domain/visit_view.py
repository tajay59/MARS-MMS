"""What the visit report template shows, built from a report's content (PRD Appendix A, as the
board; TRD 11.1; W16-10). No I/O: pictures arrive as data URIs the job prepared.

Every time is written in the zone of the station it belongs to, with the zone's abbreviation
(RPT-9); the summary and header use the first station's zone, as the visit's emails do. Only
shared elements print (W17-1): the same PDF goes to staff and to the client.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain import content as content_rules

Pictures = Mapping[str, str | None]  # media_id -> JPEG data URI, None if not ready


def moment(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def local(value: Any, zone: str | None) -> str:
    """`05 Oct 2026, 14:05 EST`, or UTC when the station has no zone."""
    when = moment(value)
    if when is None:
        return "-"
    try:
        shown = when.astimezone(ZoneInfo(zone)) if zone else when.astimezone(UTC)
    except Exception:  # noqa: BLE001 - an unknown zone name must not stop a report
        shown = when.astimezone(UTC)
    return f"{shown.day:02d} {shown:%b %Y}, {shown:%H:%M} {shown.tzname()}"


def _image(m: Mapping[str, Any], pictures: Pictures) -> dict[str, Any]:
    return {
        "media_id": m["media_id"], "caption": m.get("caption"), "filename": m["filename"],
        "uri": pictures.get(m["media_id"]), "taken": m.get("captured_at"),
    }


def build(
    report: Mapping[str, Any], pictures: Pictures, *, app_url: str, generated_at: datetime
) -> dict[str, Any]:
    content = report["content"]
    facts, narrative = content["facts"], content["narrative"]
    visit = facts["visit"]
    first_zone = next((s["time_zone"] for s in facts["stations"] if s.get("time_zone")), None)
    in_body = {s["media_id"] for s in content["media_selection"] if s["in_body"]}
    captions = {s["media_id"]: s["caption"] for s in content["media_selection"]}
    stories = {s["station_id"]: s["work_performed"] for s in narrative["stations"]}
    appendix: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    stations: list[dict[str, Any]] = []

    def shown(
        entries: list[Mapping[str, Any]], station_zone: str | None, s_code: str
    ) -> list[dict[str, Any]]:
        out = []
        for m in entries:
            if m["kind"] == "video":
                videos.append({
                    "caption": captions.get(m["media_id"]) or m.get("caption"),
                    "filename": m["filename"], "poster": pictures.get(f"poster:{m['media_id']}"),
                    "station": s_code,
                    "link": f"{app_url.rstrip('/')}/visits/{visit['id']}/media/{m['media_id']}",
                })
            elif m["kind"] == "image":
                item = _image({**m, "caption": captions.get(m["media_id"], m.get("caption"))},
                              pictures)
                item["taken"] = local(m.get("captured_at"), station_zone)
                if m["media_id"] in in_body:
                    out.append(item)
                else:
                    appendix.append(item)
        return out

    for s in facts["stations"]:
        zone = s.get("time_zone")
        tasks, notes, recs, configs = [], [], [], []
        elements = content_rules.shared_elements(s)
        for e in elements:
            sections = {k: shown(v, zone, s["code"]) for k, v in e["media"].items()}
            if e["kind"] == "task":
                items = e["items"]
                tasks.append({
                    "title": e["title"], "description": e.get("description"), "items": items,
                    "incomplete": any(not i["done"] for i in items),
                    "before": sections.get("before", []), "after": sections.get("after", []),
                })
            elif e["kind"] == "note":
                notes.append({"title": e["title"], "description": e.get("description"),
                              "images": sections.get("main", [])})
            elif e["kind"] == "recommendation":
                recs.append({"title": e["title"], "description": e.get("description"),
                             "priority": e.get("priority"), "request_ref": e.get("request_ref"),
                             "images": sections.get("main", [])})
            else:
                configs.append({
                    "title": e["title"], "description": e.get("description"),
                    "versions": e["config_versions"],
                    "before": sections.get("before", []), "after": sections.get("after", []),
                })
        stations.append({
            "code": s["code"], "name": s["name"], "type": s.get("type"),
            "country": s.get("country"), "zone": zone,
            "coordinates": (f"{s['latitude']:.5f}, {s['longitude']:.5f}"
                            if s.get("latitude") is not None and s.get("longitude") is not None
                            else None),
            "elevation_m": s.get("elevation_m"), "parameters": s.get("parameters", []),
            "owner": (s.get("owner") or {}).get("name"),
            "arrived": local(s.get("arrived_at"), zone),
            "departed": local(s.get("departed_at"), zone),
            "tasks": tasks, "notes": notes, "recommendations": recs, "configs": configs,
            "work_performed": stories.get(s["station_id"]) or "",
            "empty": not elements,
        })
    extra = visit.get("additional_visit_required")
    return {
        "number": report["number"], "version": report["version"],
        "draft": report["status"] == "draft",
        "status_word": "Draft" if report["status"] == "draft" else "Final",
        "generated": local(generated_at, first_zone),
        "org_name": visit.get("org_name"), "request_ref": visit["request_ref"],
        "request_title": visit.get("request_title"),
        "started": local(visit.get("started_at"), first_zone),
        "ended": local(visit.get("ended_at"), first_zone),
        "staff": [{"name": p["name"], "lead": p["id"] == visit["lead_staff_id"]}
                  for p in visit["staff"]],
        "outcome": "Additional visit required" if extra else "All work complete",
        "summary": narrative.get("summary") or "",
        "stations": stations, "videos": videos, "appendix": appendix,
        "recommendations": narrative.get("recommendations") or "",
        "follow_up": narrative.get("follow_up") or "",
        "calibrations_due": [
            {"code": s["code"], "due": local(s["next_calibration_due_at"], s.get("time_zone"))}
            for s in facts["stations"] if s.get("next_calibration_due_at")
        ],
        "signatures": [],
        "no_work": all(st["empty"] for st in stations),
    }
