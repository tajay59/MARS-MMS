"""Who signs a visit report and what a drawn signature must be (TRD 11.3; PRD RPT-4, RPT-5;
W17-5, W17-6). No I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mms_common.signature import NAME_MAX, NAME_MIN, PNG_END, PNG_MAGIC, png_bytes, typed_name

__all__ = [
    "NAME_MAX", "NAME_MIN", "PNG_END", "PNG_MAGIC", "new_signature", "png_bytes", "role_of",
    "typed_name",
]


def role_of(report: Mapping[str, Any], user_id: str) -> str | None:
    """`lead`, `attending`, or None when the person did not attend the visit (an admin who did
    not attend does not sign)."""
    if user_id == report["lead_staff_id"]:
        return "lead"
    return "attending" if user_id in report["staff_ids"] else None


def new_signature(
    *, signature_id: str, report: Mapping[str, Any], user_id: str, role: str, name: str,
    typed: str, image: bytes, attestation: str, signed_at: Any, ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    """The record, bound to the report version and the content as it was when signed."""
    return {
        "_id": signature_id, "report_id": report["_id"], "report_version": report["version"],
        "signer_id": user_id, "signer_name": name, "role": role, "typed_name": typed,
        "image": image, "attestation": attestation, "signed_at": signed_at,
        "ip": ip, "user_agent": user_agent, "content_hash": report["content_hash"],
        "content_version": report["content_version"], "valid": True, "cleared_at": None,
        "cleared_by": None,
    }
