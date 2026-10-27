"""How a report record is shown to a caller (rule 6): staff see the draft whole, with its
signatures; a client sees a final report of their own organization, with the staff-only elements
taken out and no signature image, hash or attendee id."""

from __future__ import annotations

import base64
from typing import Any

from mms_common.auth import User
from mms_common.errors import NotFound

from app.api.report_schemas import PdfState, ReportOut, SignatureOut
from app.domain import content as content_rules
from app.domain import drafts


def pdf_state(doc: dict[str, Any]) -> PdfState:
    final = doc.get("final_pdf")
    if final and doc["status"] in ("final", "superseded"):
        return PdfState(state="ready", current=True, pages=final["pages"], rendered_at=final["at"])
    if doc["status"] == "finalizing":
        return PdfState(state="rendering", current=True)
    pdf, render = doc.get("draft_pdf"), doc["render"]
    if render["state"] in ("queued", "running"):
        state = "rendering"
    elif render["state"] == "failed":
        state = "failed"
    else:
        state = "ready" if pdf else "none"
    return PdfState(
        state=state, current=drafts.pdf_is_current(doc),
        pages=pdf["pages"] if pdf else None, rendered_at=pdf["at"] if pdf else None,
        error=render.get("error"),
    )


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["_id"], "type": doc["type"], "subject_ref": doc["subject_ref"],
        "visit_id": doc.get("visit_id"), "request_id": doc["request_id"], "number": doc["number"],
        "version": doc["version"], "status": doc["status"], "pdf": pdf_state(doc),
        "awaiting_media": len(doc.get("awaiting_media", [])), "drafted_at": doc.get("drafted_at"),
        "finalized_at": doc.get("finalized_at"), "pdf_sha256": doc.get("pdf_sha256"),
        "created_at": doc["created_at"], "updated_at": doc["updated_at"],
    }


def visible(user: User, doc: dict[str, Any] | None) -> dict[str, Any]:
    """Staff read everything; a client only a final report of their organization (rule 6). Out
    of scope is 404, never 403 (rule 4)."""
    if doc is None:
        raise NotFound()
    if user.is_client and not (doc["status"] == "final" and doc["org_id"] == user.org_id):
        raise NotFound()
    return doc


def signature_out(doc: dict[str, Any]) -> SignatureOut:
    image = (
        "data:image/png;base64," + base64.b64encode(bytes(doc["image"])).decode()
        if doc["valid"] else None
    )
    return SignatureOut(
        id=doc["_id"], signer_id=doc["signer_id"], role=doc["role"],
        signer_name=doc["signer_name"], typed_name=doc["typed_name"],
        attestation=doc["attestation"], signed_at=doc["signed_at"],
        content_version=doc["content_version"], valid=doc["valid"],
        cleared_at=doc.get("cleared_at"), cleared_by=doc.get("cleared_by"), image=image,
    )


def report_out(
    user: User, doc: dict[str, Any], signed: list[dict[str, Any]], attestation: str
) -> ReportOut:
    """`signed` is every signature of the report; only this version's are shown."""
    if user.is_client:
        return ReportOut(**summary(doc), content_version=doc["content_version"],
                         facts_version=doc["facts_version"],
                         content=content_rules.client_view(doc["content"]))
    return ReportOut(
        **summary(doc), content_version=doc["content_version"],
        facts_version=doc["facts_version"], content=doc["content"],
        content_hash=doc.get("content_hash"), lead_staff_id=doc["lead_staff_id"],
        staff_ids=list(doc["staff_ids"]), attestation=attestation,
        finalized_by=doc.get("finalized_by"), finalize_error=doc.get("finalize_error"),
        supersedes_id=doc.get("supersedes_id"),
        signatures=[signature_out(d) for d in signed if d["report_version"] == doc["version"]],
    )
