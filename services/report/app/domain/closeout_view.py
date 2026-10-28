"""What the close-out template shows, built from operations' facts (PRD RPT-8; W18-11). No I/O.

Every time is written in the zone of the first station that has one, with the zone's abbreviation
(RPT-9). Only what operations already filtered arrives: comments a client may read, report numbers
and versions. No visit-board element text is in the facts, so none can be printed (W17-1).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.domain import closeout
from app.domain.visit_view import local, moment

DAY_S = 86_400


def label(status: str | None) -> str:
    """`client_review` as `Client Review`."""
    return (status or "-").replace("_", " ").title()


def _days_waited(decision: Mapping[str, Any]) -> int | None:
    started, ended = moment(decision.get("reviewing")), moment(decision.get("at"))
    if started is None or ended is None:
        return None
    return int((ended - started).total_seconds() // DAY_S)


def _decision(decision: Mapping[str, Any] | None, zone: str | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    outcome = decision["outcome"]
    closed_by_system = outcome == "auto_closed"
    days = _days_waited(decision)
    waited = f" after {days} days without a response" if days else " without a response"
    return {
        "outcome": outcome, "accepted": outcome == "accepted", "automatic": closed_by_system,
        "by": decision.get("by_name"), "at": local(decision["at"], zone),
        "comment": decision.get("comment"), "typed_name": decision.get("typed_name"),
        "attestation": decision.get("attestation"),
        "signature": (
            "data:image/png;base64," + decision["signature_png_b64"]
            if decision.get("signature_png_b64") else None
        ),
        "sentence": (
            f"Closed automatically on {local(decision['at'], zone)}{waited}."
            if closed_by_system else None
        ),
    }


def build(
    report: Mapping[str, Any], facts: Mapping[str, Any], *, app_url: str, generated_at: datetime,
    corrections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    stations = facts["stations"]
    zone = next((s["time_zone"] for s in stations if s.get("time_zone")), None)
    base = app_url.rstrip("/")
    request = facts["request"]
    return {
        "number": report["number"], "version": report["version"],
        "org_name": request.get("org_name"), "request_ref": request["ref"],
        "request_title": request["title"], "category": label(request["category"]),
        "priority": label(request["priority"]), "requested_by": request.get("requester_name"),
        "requested": local(request["created_at"], zone),
        "closed": local((request.get("milestones") or {}).get("closed_at"), zone),
        "stations": [{"code": s["code"], "name": s["name"]} for s in stations],
        "decision": _decision(facts.get("decision"), zone),
        "timeline": [
            {"status": label(h["to"]), "at": local(h["at"], zone),
             "by": h.get("by_name") or "System", "note": h.get("note") or ""}
            for h in facts["timeline"]
        ],
        "visits": [
            {"ref": v["ref"], "lead": v.get("lead_name"),
             "dates": f"{local(v.get('started_at'), zone)} to {local(v.get('ended_at'), zone)}",
             "version": v.get("report_version"),
             "link": f"{base}/visit-reports/{v['report_id']}" if v.get("report_id") else None}
            for v in facts["visits"]
        ],
        "client_reports": [
            {"title": r["title"], "kind": "Online form" if r["kind"] == "form" else "PDF",
             "date": local(r["report_date"], None).split(",")[0],
             "by": r["submitted_by_name"], "link": f"{base}/requests/{request['id']}"}
            for r in facts.get("client_reports", [])
        ],
        "comments": [
            {"author": c["author_name"], "role": label(c["author_role"]),
             "at": local(c["created_at"], zone), "body": c["body"]}
            for c in facts["comments"]
        ],
        "corrections": [
            {"ref": c["ref"], "from": c["from"], "to": c["to"], "at": local(c["at"], zone)}
            for c in corrections
        ],
        "generated": local(generated_at, zone),
        "hash": closeout.short(report.get("content_hash")),
    }
