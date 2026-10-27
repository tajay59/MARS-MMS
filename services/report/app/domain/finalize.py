"""Finalizing and reopening a visit report: who may, what must be true, and how the saga ends
(TRD 11.2; PRD RPT-4 to RPT-6; W17-5, W17-7, W17-10). No I/O.

The saga itself is `jobs/finalize.py`. Its steps, in order, with the state each leaves behind:

1. `finalizing`: the draft stops taking edits (anything but `draft` refuses them);
2. the visit is locked for this report version (operations, idempotent);
3. the facts are read again and hashed; if what prints changed, the signatures are cleared and the
   report is a draft again (`facts_changed`);
4. the final PDF is drawn and stored under a key of its own, and in one transaction the report
   becomes `final` and `report.finalized` is added to the outbox.

A failure at 2 or 4 returns the report to `draft` with its signatures kept (the content did not
change) and unlocks the visit. A report left in `finalizing` is taken up again by a cron.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from mms_common.errors import Conflict, Forbidden, ValidationFailed

REASON_MIN, REASON_MAX = 5, 500
HASH_IN_FOOTER = 16  # the first characters of the content hash printed in the footer


def final_key(report_id: str, version: int) -> str:
    """Never reused: the report id is one version's own."""
    return f"visits/{report_id}/final-v{version}.pdf"


def short_hash(content_hash: str | None) -> str | None:
    return content_hash[:HASH_IN_FOOTER] if content_hash else None


def may_finalize(report: Mapping[str, Any], user_id: str, *, is_admin: bool) -> None:
    """The lead or an admin starts it. Raises `Forbidden` for anyone else."""
    if not is_admin and user_id != report["lead_staff_id"]:
        raise Forbidden("Only the lead or an admin can finalize", code="not_lead")


def lead_signature(
    signed: Sequence[Mapping[str, Any]], report: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    """The lead's valid signature for exactly the content as it is now."""
    for s in signed:
        if (s["valid"] and s["signer_id"] == report["lead_staff_id"]
                and s["content_hash"] == report["content_hash"]):
            return s
    return None


def check_ready(report: Mapping[str, Any], signed: Sequence[Mapping[str, Any]]) -> None:
    """Raises `Conflict` unless the draft can be finalized now."""
    if report["status"] != "draft":
        raise Conflict("Only a draft can be finalized", code="not_a_draft")
    if report["content"]["narrative"] is None or report.get("content_hash") is None:
        raise Conflict("The draft is still being prepared", code="draft_not_ready")
    if lead_signature(signed, report) is None:
        raise Conflict("The lead has to sign this version first", code="lead_not_signed")


def backoff(attempts: int, base_s: int) -> int:
    """Seconds to wait after the `attempts`th try failed: the base, then double it each time."""
    return int(base_s * 2 ** max(attempts - 1, 0))


def out_of_tries(attempts: int, retries: int) -> bool:
    return attempts >= retries


def is_stuck(report: Mapping[str, Any], now: datetime, timeout_s: int) -> bool:
    started = report.get("finalizing_at")
    return bool(
        report["status"] == "finalizing" and started is not None
        and now >= started + timedelta(seconds=timeout_s)
    )


def reopen_reason(text: str) -> str:
    reason = " ".join(text.split())
    if not REASON_MIN <= len(reason) <= REASON_MAX:
        raise ValidationFailed(
            f"Give a reason ({REASON_MIN} to {REASON_MAX} characters)", code="bad_reason",
            field="reason")
    return reason


def reopened_draft(
    old: Mapping[str, Any], *, report_id: str, reason: str, by: str, now: datetime
) -> dict[str, Any]:
    """Version n+1 of a final report: the narrative and photo choice are kept, the facts are read
    again (stale), nothing is signed. The visit is still locked for the old version until
    `unlock_pending` is done."""
    return {
        "_id": report_id, "type": old["type"], "subject_ref": old["subject_ref"],
        "visit_id": old["visit_id"], "request_id": old["request_id"], "org_id": old["org_id"],
        "number": old["number"], "version": old["version"] + 1, "status": "draft",
        "staff_ids": list(old["staff_ids"]), "lead_staff_id": old["lead_staff_id"],
        "content": {
            "facts": old["content"]["facts"], "narrative": old["content"]["narrative"],
            "media_selection": [dict(s) for s in old["content"]["media_selection"]],
        },
        "content_version": 1, "facts_version": old["facts_version"], "facts_stale": True,
        "facts_stale_at": now, "awaiting_media": [], "ended_at": old["ended_at"],
        "content_hash": old["content_hash"], "template_version": old["template_version"],
        "draft_pdf": None, "render": {"state": "idle", "attempts": 0, "error": None},
        "pdf_key": None, "pdf_sha256": None, "final_pdf": None, "finalize_attempts": 0,
        "finalize_error": None, "finalizing_at": None, "finalized_at": None, "finalized_by": None,
        "supersedes_id": old["_id"], "reopened_reason": reason, "reopened_by": by,
        "unlock_pending": {"report_id": old["_id"], "version": old["version"]},
        "reminders_sent": [], "remind_from": now,
        "drafted_at": old.get("drafted_at"), "created_at": now, "updated_at": now,
    }
