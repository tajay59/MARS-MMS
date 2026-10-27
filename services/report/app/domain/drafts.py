"""A visit report draft's rules (TRD 11.2 steps 1 and 2; PRD RPT-1; W16-3 to W16-5). No I/O.

The draft's `content` has three parts: `facts` (operations' board, frozen when read and
refreshed while the report is a draft), `narrative` (what people write; pre-filled once) and
`media_selection` (which photos print in the body). A facts refresh never touches the narrative
(decision W16-4).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

TEMPLATE_VERSION = "visit-1"
PER_STATION_IN_BODY = 6  # TRD 11.1: the rest go in the appendix
FACTS_VERSION = 1  # the shape of operations' `report-facts` this release reads

# A file in one of these states will not change by waiting
SETTLED = frozenset({"ready", "failed", "deleted"})


def media_refs(facts: Mapping[str, Any], *, shared_only: bool = False) -> list[dict[str, Any]]:
    """Every file on the visit's boards, in board order: where it is and what it is. A report
    prints only shared elements (W17-1), so what it picks and waits for is `shared_only`."""
    out: list[dict[str, Any]] = []
    for station in facts["stations"]:
        for element in station["elements"]:
            if shared_only and not element.get("shared"):
                continue
            for section, entries in element["media"].items():
                for m in entries:
                    out.append({
                        "station_id": station["station_id"], "element_id": element["id"],
                        "element_kind": element["kind"], "section": section,
                        "media_id": m["media_id"], "kind": m["kind"], "filename": m["filename"],
                        "caption": m.get("caption"), "captured_at": m.get("captured_at"),
                    })
    return out


def pending_media(facts: Mapping[str, Any], statuses: Mapping[str, str | None]) -> list[str]:
    """Files still being checked or processed. A file media does not know is not waited for, and
    neither is one that will not print."""
    return [
        r["media_id"] for r in media_refs(facts, shared_only=True)
        if statuses.get(r["media_id"]) not in SETTLED | {None}
    ]


def default_narrative(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Pre-filled from the board's shared Notes and Recommendations and the follow-up notes
    (TRD 11.2; W17-1). People change it in the editor; a refresh of the facts never rewrites it."""
    stations = []
    recommendations: list[str] = []
    for station in facts["stations"]:
        work = []
        for e in station["elements"]:
            if not e.get("shared"):
                continue
            if e["kind"] == "note":
                work.append(e["title"] + (f": {e['description']}" if e.get("description") else ""))
            elif e["kind"] == "recommendation":
                label = f" ({e['priority']})" if e.get("priority") else ""
                recommendations.append(f"{station['code']}: {e['title']}{label}")
        stations.append({"station_id": station["station_id"], "work_performed": "\n".join(work)})
    return {
        "summary": "",
        "stations": stations,
        "recommendations": "\n".join(recommendations),
        "follow_up": facts["visit"].get("follow_up_notes") or "",
    }


def default_media_selection(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Photos only (video has its own section): a Task's first Before and first After photo
    first, then the rest in board order, at most `PER_STATION_IN_BODY` in each station's body."""
    selection: list[dict[str, Any]] = []
    for station in facts["stations"]:
        photos = [r for r in media_refs(facts, shared_only=True)
                  if r["station_id"] == station["station_id"] and r["kind"] == "image"]
        first: dict[tuple[str, str], str] = {}
        for r in photos:
            if r["element_kind"] == "task" and r["section"] in ("before", "after"):
                first.setdefault((r["element_id"], r["section"]), r["media_id"])
        picked = list(first.values())
        ordered = [r for r in photos if r["media_id"] in picked] + [
            r for r in photos if r["media_id"] not in picked]
        for index, r in enumerate(ordered):
            selection.append({
                "station_id": r["station_id"], "element_id": r["element_id"],
                "section": r["section"], "media_id": r["media_id"], "caption": r["caption"],
                "in_body": index < PER_STATION_IN_BODY,
            })
    return selection


def refreshed_selection(
    selection: list[dict[str, Any]], facts: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """After a facts refresh: files no longer on the board (or no longer shared) leave the
    selection, new photos join
    it in the appendix, and what people chose stays as it is (W16-4)."""
    photos = {r["media_id"]: r for r in media_refs(facts, shared_only=True)
              if r["kind"] == "image"}
    kept = [s for s in selection if s["media_id"] in photos]
    known = {s["media_id"] for s in kept}
    for media_id, r in photos.items():
        if media_id not in known:
            kept.append({
                "station_id": r["station_id"], "element_id": r["element_id"],
                "section": r["section"], "media_id": media_id, "caption": r["caption"],
                "in_body": False,
            })
    return kept


def new_draft(
    *, report_id: str, number: str, subject_ref: str, visit_id: str, request_id: str, org_id: str,
    staff_ids: list[str], lead_staff_id: str, ended_at: datetime, now: datetime,
) -> dict[str, Any]:
    """The record made on `visit.ended`: no content yet; the facts are read by `jobs/drafts`."""
    return {
        "_id": report_id, "type": "visit", "subject_ref": subject_ref, "visit_id": visit_id,
        "request_id": request_id, "org_id": org_id, "number": number, "version": 1,
        "status": "draft", "staff_ids": staff_ids, "lead_staff_id": lead_staff_id,
        "content": {"facts": None, "narrative": None, "media_selection": []},
        "content_version": 1, "facts_version": 0, "facts_stale": True, "facts_stale_at": now,
        "awaiting_media": [], "ended_at": ended_at,
        "content_hash": None, "template_version": TEMPLATE_VERSION,
        "draft_pdf": None, "render": {"state": "idle", "attempts": 0, "error": None},
        "pdf_key": None, "pdf_sha256": None, "finalize_attempts": 0, "finalize_error": None,
        "finalized_at": None, "finalized_by": None, "supersedes_id": None, "drafted_at": None,
        "created_at": now, "updated_at": now,
    }


def pdf_is_current(report: Mapping[str, Any]) -> bool:
    pdf = report.get("draft_pdf")
    if not pdf:
        return False
    return bool(
        pdf["content_version"] == report["content_version"]
        and pdf["facts_version"] == report["facts_version"]
    )


def ready_to_render(
    report: Mapping[str, Any], now: datetime, wait: timedelta
) -> bool:
    """The first PDF is drawn when the facts are read and every file is processed, or when
    `wait` has passed since the visit ended (TRD 3.4: up to five minutes for `media.processed`).
    Later PDFs are drawn when someone asks for a preview."""
    if report["status"] != "draft" or report["draft_pdf"] is not None:
        return False
    if report["facts_stale"] or report["content"]["facts"] is None:
        return False
    if report["render"]["state"] != "idle":
        return False
    return not report["awaiting_media"] or now >= report["ended_at"] + wait
