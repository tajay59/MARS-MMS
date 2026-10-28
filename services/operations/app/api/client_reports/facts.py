"""What the report service needs to draw a client's online-form report (PRD CRP-3; W18-10).

`GET /internal/client-reports/{id}` is the one read it makes after `client_report.submitted`:
the event names the report, and the text is read here, because events never carry it (rule 1).
Only a submitted form report has facts: a draft is private to its author.
"""

from __future__ import annotations

from typing import Any

from app.api.context import Ctx
from app.repo import client_reports as repo
from app.repo.requests import requests as request_repo
from app.repo.stations import orgs
from app.repo.stations import stations as station_repo

FACTS_VERSION = 1


async def build(ctx: Ctx, report_id: str) -> dict[str, Any] | None:
    doc = await repo.get(ctx.db, report_id)
    if doc is None or doc["status"] != "submitted" or doc["kind"] != "form":
        return None
    request = await request_repo.get(ctx.db, doc["request_id"])
    if request is None:
        return None
    org = await orgs.get(ctx.db, doc["org_id"])
    details = await station_repo.by_ids(ctx.db, doc["station_ids"])
    form = doc["form"]
    return {
        "facts_version": FACTS_VERSION,
        "client_report_id": doc["_id"], "attempt": doc["attempt"],
        "request": {"id": request["_id"], "ref": request["ref"], "title": request["title"]},
        "org_id": doc["org_id"], "org_name": (org or {}).get("name"),
        "title": doc["title"], "report_date": doc["report_date"],
        "submitted_by_name": doc["submitted_by_name"], "submitted_at": doc["submitted_at"],
        "stations": [
            {"station_id": i, "code": d["code"], "name": d["name"], "country": d["country"],
             "time_zone": d.get("time_zone")}
            for i in doc["station_ids"] if (d := details.get(i))
        ],
        "summary": form["summary"], "observations": list(form["observations"]),
        "data_quality_notes": form["data_quality_notes"],
        "images": [{"media_id": i["media_id"], "name": i["name"]} for i in form["images"]],
    }
