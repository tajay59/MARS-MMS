"""What the report service needs to write a request's close-out report (PRD RPT-8; TRD 3.4;
W18-11).

`GET /internal/requests/{id}/closeout-facts` is the one read the report service makes for it,
after `request.closed`. The event says the request closed and how; the decision, its drawn
signature and the comments are read here, because events never carry them (rule 1; W18-3).
Internal comments are left out in the repository read (rule 6): a close-out is one document
for staff and client alike. Plain JSON, versioned by `facts_version`.
"""

from __future__ import annotations

import base64
from typing import Any

from app.api.context import Ctx
from app.repo.requests import comments as comment_repo
from app.repo.requests import requests as request_repo
from app.repo.stations import orgs
from app.repo.stations import stations as station_repo
from app.repo.visits import visits as visit_repo

FACTS_VERSION = 1


def _decision(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    signed = doc.get("signature") or {}
    image = signed.get("image")
    return {
        "outcome": doc["outcome"], "by_id": doc.get("by"), "by_name": doc.get("by_name"),
        "at": doc["at"], "comment": doc.get("comment"),
        "typed_name": signed.get("typed_name"), "attestation": signed.get("attestation"),
        "signature_png_b64": base64.b64encode(image).decode() if image else None,
        "reports": doc.get("reports", []),
    }


async def build(ctx: Ctx, request_id: str) -> dict[str, Any] | None:
    request = await request_repo.get(ctx.db, request_id)
    if request is None:
        return None
    org = await orgs.col(ctx.db).find_one({"_id": request["org_id"]}, {"name": 1})
    details = await station_repo.by_ids(ctx.db, request["station_ids"])
    visits = await visit_repo.for_request(ctx.db, request_id, None)
    talk = comment_repo.col(ctx.db).find({"request_id": request_id, "internal": False}).sort(
        "_id", 1)
    return {
        "facts_version": FACTS_VERSION,
        "request": {
            "id": request["_id"], "ref": request["ref"], "title": request["title"],
            "description": request["description"], "category": request["category"],
            "priority": request["priority"], "status": request["status"],
            "org_id": request["org_id"], "org_name": (org or {}).get("name"),
            "requester_name": request.get("requester_name"),
            "created_at": request["created_at"], "milestones": request.get("milestones", {}),
            "reopen_count": request.get("reopen_count", 0),
        },
        "stations": [
            {"station_id": i, "code": d["code"], "name": d["name"], "country": d["country"],
             "time_zone": d.get("time_zone")}
            for i in request["station_ids"] if (d := details.get(i))
        ],
        "timeline": [
            {"from": h.get("from"), "to": h["to"], "at": h["at"], "by_name": h.get("by_name"),
             "note": h.get("note")}
            for h in request["status_history"]
        ],
        "visits": [
            {"visit_id": v["_id"], "ref": v["ref"], "status": v["status"],
             "started_at": v.get("started_at"), "ended_at": v.get("ended_at"),
             "lead_name": next((p["name"] for p in v.get("staff", [])
                                if p["id"] == v["lead_staff_id"]), None),
             "report_id": v.get("report_id"), "report_version": v.get("report_version"),
             "report_status": v.get("report_status")}
            for v in visits if v["status"] != "cancelled"
        ],
        "comments": [
            {"author_name": c["author_name"], "author_role": c["author_role"], "body": c["body"],
             "created_at": c["created_at"]}
            async for c in talk
        ],
        "decision": _decision(request.get("client_verification")),
    }
