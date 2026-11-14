"""What the report service needs to write a visit's report (TRD 11.2 step 1; W16-2).

`GET /internal/visits/{id}/report-facts` is the one read the report service makes of operations
for a draft: the visit, its request, its stations and every live element of their boards with its
content and file entries. The events say a board changed and never carry its text (rule 1 leaves
the report no other way to read it). It is a service-to-service read for staff-side documents, so
nothing is filtered by audience here: the report service decides who sees a report (rule 6), and
a draft is staff only.

The shape is plain JSON, versioned by `facts_version`, so a report made by an older release can
still be read by a newer one.
"""

from __future__ import annotations

from typing import Any

from app.api.context import Ctx
from app.repo.requests import requests as request_repo
from app.repo.stations import orgs, units
from app.repo.stations import stations as station_repo
from app.repo.visits import elements as element_repo
from app.repo.visits import visits as visit_repo

FACTS_VERSION = 1


def _element(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["_id"], "kind": doc["kind"], "title": doc["title"],
        "description": doc.get("description"),
        "items": [{"id": i["id"], "text": i["text"], "done": i["done"]}
                  for i in doc.get("items", [])],
        "priority": doc.get("priority"), "shared": bool(doc.get("shared")),
        "request_ref": doc.get("request_ref"),
        "config_versions": [
            {"station_id": v.get("station_id"), "version": v.get("version"),
             "note": v.get("note"), "files": v.get("files", [])}
            for v in doc.get("config_versions", [])
        ],
        "media": {
            section: [
                {k: m.get(k) for k in ("media_id", "kind", "filename", "caption", "captured_at")}
                for m in entries if not m.get("hidden")
            ]
            for section, entries in doc.get("media", {}).items()
        },
        "created_by_name": doc.get("created_by_name"), "created_at": doc["created_at"],
        "version": doc["version"],
    }


async def build(ctx: Ctx, visit_id: str) -> dict[str, Any] | None:
    visit = await visit_repo.get(ctx.db, visit_id)
    if visit is None:
        return None
    request = await request_repo.require(ctx.db, visit["request_id"])
    station_ids = [s["station_id"] for s in visit["stations"]]
    details = await station_repo.by_ids(ctx.db, station_ids)
    due = await units.next_due_by_station(ctx.db, station_ids)
    live = await element_repo.for_visits(ctx.db, [visit_id])
    org = await orgs.col(ctx.db).find_one({"_id": request["org_id"]}, {"name": 1})
    staff_names = {p["id"]: p["name"] for p in visit.get("staff", [])}
    by_station: dict[str, list[dict[str, Any]]] = {}
    for doc in sorted(live, key=lambda d: (d["created_at"], d["_id"])):
        by_station.setdefault(doc["station_id"], []).append(_element(doc))
    stations = []
    for s in visit["stations"]:
        info = details.get(s["station_id"], {})
        lon, lat = (info.get("location") or {}).get("coordinates") or (None, None)
        stations.append({
            "station_id": s["station_id"], "code": info.get("code") or s.get("station_code"),
            "name": info.get("name") or s.get("station_name"), "type": info.get("type"),
            "country": info.get("country"),
            "time_zone": info.get("time_zone") or s.get("time_zone"),
            "latitude": lat, "longitude": lon, "elevation_m": info.get("elevation_m"),
            "parameters": list(info.get("parameters", [])),
            "owner": {"id": s["owner_staff_id"], "name": staff_names.get(s["owner_staff_id"])},
            "arrived_at": s.get("arrived_at"), "departed_at": s.get("departed_at"),
            "next_calibration_due_at": due.get(s["station_id"]),
            "elements": by_station.get(s["station_id"], []),
        })
    return {
        "facts_version": FACTS_VERSION,
        "visit": {
            "id": visit["_id"], "ref": visit["ref"], "status": visit["status"],
            "version": visit["version"], "request_id": request["_id"],
            "request_ref": request["ref"], "request_title": request.get("title"),
            "org_id": request["org_id"], "org_name": (org or {}).get("name"),
            "planned_start": visit["planned_start"], "planned_end": visit["planned_end"],
            "started_at": visit.get("started_at"), "ended_at": visit.get("ended_at"),
            "additional_visit_required": visit.get("additional_visit_required"),
            "follow_up_notes": visit.get("follow_up_notes"),
            "lead_staff_id": visit["lead_staff_id"], "staff": list(visit.get("staff", [])),
            "locked": bool(visit.get("locked")),
        },
        "stations": stations,
    }
