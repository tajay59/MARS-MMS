"""A client's online-form report as a PDF (PRD CRP-3; TRD 11.1; W18-10). No I/O.

The client submits the form in operations; the report service makes a `client_form` report from
`client_report.submitted`: a record at once (so the number is fixed and a repeat of the event
changes nothing), the PDF a little later in the worker. It is `final` as soon as the PDF exists:
nobody edits or signs it (the client already sent it, CRP-4), and it is never reopened. Only one
thing moves it again: a try that fails three times (`render_failed`), after which the client may
submit it once more and the same record is drawn again.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.domain.finalize import short_hash

TEMPLATE_VERSION = "client-form-1"
TYPE = "client_form"
FACTS_VERSION = 1  # the shape of operations' `GET /internal/client-reports/{id}` read here

# Where the record stands while the PDF is drawn, and after
RENDERING = "rendering"
FINAL = "final"
FAILED = "render_failed"


def subject_ref(client_report_id: str) -> str:
    return f"client_report:{client_report_id}"


def number(request_ref: str, sequence: int) -> str:
    """`CR-2026-0042-01`: the request's number and this being the first client report on it
    (a request is `MR-2026-0042`)."""
    return f"CR-{request_ref.removeprefix('MR-')}-{sequence:02d}"


def counter_key(request_id: str) -> str:
    return f"client_form:{request_id}"


def final_key(report_id: str, attempt: int) -> str:
    """Never reused: a second try of the same report draws to a key of its own."""
    return f"client-forms/{report_id}/final-{attempt}.pdf"


def content_hash(facts: Mapping[str, Any]) -> str:
    """SHA-256 of what prints, as canonical JSON. The first characters go in the footer."""
    canonical = json.dumps(
        {k: v for k, v in facts.items() if k != "attempt"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def new_report(
    *, report_id: str, client_report_id: str, report_number: str, request_id: str, org_id: str,
    submitted_by: str, attempt: int, now: datetime,
) -> dict[str, Any]:
    """The record made on `client_report.submitted`: no content yet, the facts are read by the
    job. The shape is a visit report's where it matters to the shared routes (list, read,
    download, verify) and empty where it does not."""
    return {
        "_id": report_id, "type": TYPE, "subject_ref": subject_ref(client_report_id),
        "client_report_id": client_report_id, "visit_id": None, "request_id": request_id,
        "org_id": org_id, "number": report_number, "version": 1, "status": RENDERING,
        "staff_ids": [], "lead_staff_id": None, "content": {"form": None},
        "content_version": 1, "facts_version": 1, "content_hash": None,
        "awaiting_media": [], "template_version": TEMPLATE_VERSION, "draft_pdf": None,
        "render": {"state": "idle", "attempts": 0, "error": None}, "attempt": attempt,
        "pdf_key": None, "pdf_sha256": None, "final_pdf": None, "finalized_at": None,
        "finalized_by": submitted_by, "supersedes_id": None, "drafted_at": None,
        "created_at": now, "updated_at": now,
    }


def can_try_again(report: Mapping[str, Any], attempt: int) -> bool:
    """The client submitted a report whose PDF failed once more (a higher attempt)."""
    return bool(report["status"] == FAILED and attempt > int(report["attempt"]))


def short(content_hash_: str | None) -> str | None:
    return short_hash(content_hash_)
