"""A request's close-out report (PRD RPT-8, RPT-6; TRD 11.1; decisions W18-11, W18-12). No I/O.

The close-out is made by the report service when `request.closed` arrives: a record at once (its
number, its state, nothing drawn) and the PDF a little later in the worker, from the facts
operations holds (the request, its timeline, the visit reports in force, the client reports, the
comments a client may read, and the client's decision with the drawn signature). It is `final` as
soon as the PDF exists: nobody edits or signs it, and it is never changed, only replaced.

A visit report corrected after the request closed makes version n+1 (`supersedes_id`); the one
before becomes `superseded` in the same transaction that makes the new one final. The record says
what it waits for (`expects`: the visit report versions the correction made), because the facts
come from operations a moment after the event that announces them.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.domain.finalize import short_hash

TEMPLATE_VERSION = "closeout-1"
TYPE = "closeout"
FACTS_VERSION = 2  # the shape of operations' closeout-facts this release reads (2: client reports)
WAIT_TRIES = 10  # tries spent waiting for operations to know a corrected report before drawing

RENDERING = "rendering"
FINAL = "final"
SUPERSEDED = "superseded"
FAILED = "render_failed"


def subject_ref(request_id: str) -> str:
    return f"request:{request_id}"


def number(request_ref: str) -> str:
    """`CO-2026-0042` for the request `MR-2026-0042`."""
    return f"CO-{request_ref.removeprefix('MR-')}"


def final_key(report_id: str) -> str:
    """Never reused: the report id is one version's own."""
    return f"closeouts/{report_id}/final.pdf"


def kept_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """What the record keeps of the facts: everything except the drawing itself, which operations
    holds and the PDF carries."""
    out = {k: v for k, v in facts.items() if k != "decision"}
    decision = facts.get("decision")
    if decision is not None:
        image = decision.get("signature_png_b64")
        out["decision"] = {
            **{k: v for k, v in decision.items() if k != "signature_png_b64"},
            "signature_sha256": hashlib.sha256(base64.b64decode(image)).hexdigest()
            if image else None,
        }
    return out


def content_hash(facts: Mapping[str, Any]) -> str:
    """SHA-256 of what prints, as canonical JSON, with the drawing stood in for by its own hash
    (so the record can be checked against what it keeps)."""
    canonical = json.dumps(
        kept_facts(facts), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def new_closeout(
    *, report_id: str, request_id: str, request_ref: str, title: str | None, org_id: str,
    version: int, supersedes_id: str | None, expects: Mapping[str, int], now: datetime,
) -> dict[str, Any]:
    """The record made on `request.closed` (version 1) or by a correction (version n + 1). The
    shape is a visit report's where it matters to the shared routes (list, read, download,
    verify) and empty where it does not."""
    return {
        "_id": report_id, "type": TYPE, "subject_ref": subject_ref(request_id),
        "request_id": request_id, "request_ref": request_ref, "title": title, "visit_id": None,
        "org_id": org_id, "number": number(request_ref), "version": version, "status": RENDERING,
        "staff_ids": [], "lead_staff_id": None, "content": {"closeout": None},
        "content_version": 1, "facts_version": FACTS_VERSION, "content_hash": None,
        "awaiting_media": [], "template_version": TEMPLATE_VERSION, "draft_pdf": None,
        "render": {"state": "idle", "attempts": 0, "error": None},
        "expects": dict(expects), "inputs_seq": 0, "corrections": [],
        "pdf_key": None, "pdf_sha256": None, "final_pdf": None, "finalized_at": None,
        "finalized_by": None, "supersedes_id": supersedes_id, "drafted_at": None,
        "created_at": now, "updated_at": now,
    }


def not_yet_known(expects: Mapping[str, int], facts: Mapping[str, Any]) -> bool:
    """Operations has not yet taken in a corrected report this close-out was made for: the event
    that told the report service travels faster than the one that told operations."""
    held = {v["visit_id"]: v.get("report_version") or 0 for v in facts["visits"]}
    return any(held.get(visit_id, 0) < wanted for visit_id, wanted in expects.items())


def corrections(
    before: Mapping[str, Any] | None, facts: Mapping[str, Any], at: datetime
) -> list[dict[str, Any]]:
    """The visit reports whose version in force is higher than in the close-out this one replaces
    ("Corrected report VR-… v2 replaced v1")."""
    if before is None:
        return []
    old = {v["visit_id"]: v.get("report_version") or 0 for v in before["visits"]}
    return [
        {"ref": v["ref"], "visit_id": v["visit_id"], "from": old[v["visit_id"]],
         "to": v.get("report_version") or 0, "at": at}
        for v in facts["visits"]
        if v["visit_id"] in old and (v.get("report_version") or 0) > old[v["visit_id"]]
    ]


def decide_version(latest: Mapping[str, Any] | None, *, visit_version: int) -> str:
    """What a visit report becoming final means for the close-out (the decision tree):

    - `skip`: no close-out exists (the request is not closed, or `request.closed` has not been
      read yet and will draw from the facts as they stand), or this is a first version;
    - `merge`: the latest close-out is still being drawn, so the correction joins it;
    - `new`: the latest is final, so a new version replaces it.
    """
    if latest is None or visit_version < 2:
        return "skip"
    if latest["status"] in (RENDERING, FAILED):
        return "merge"
    return "new"


def short(hash_: str | None) -> str | None:
    return short_hash(hash_)
