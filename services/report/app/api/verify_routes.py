"""Verify a report (PRD RPT-11; W17-12): is this PDF one the system issued?

Public, so someone holding a printed copy can check it. Nginx rate limits it (the `auth` zone).
The caller gives the SHA-256 of the PDF as JSON, or sends the PDF itself
(`Content-Type: application/pdf`, at most `verify_max_bytes`), which is hashed as it arrives and
never stored. The answer names the report and its version and returns no content.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Request
from mms_common.errors import AppError, ValidationFailed
from pydantic import ValidationError

from app.api.context import CtxDep
from app.api.report_schemas import VerifyIn, VerifyOut
from app.repo import reports

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class TooLarge(AppError):
    status, code, title = 413, "too_large", "That file is too large"


async def _hash_of(request: Request, limit: int) -> str:
    if request.headers.get("content-type", "").split(";")[0].strip() == "application/pdf":
        digest, size = hashlib.sha256(), 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise TooLarge(f"Send a PDF of at most {limit // (1024 * 1024)} MB")
            digest.update(chunk)
        return digest.hexdigest()
    try:
        body = VerifyIn.model_validate_json(await request.body())
    except ValidationError as e:
        raise ValidationFailed("Send the 64-character code or the PDF", code="bad_code") from e
    return body.sha256.lower()


@router.post("/verify")
async def verify(request: Request, ctx: CtxDep) -> VerifyOut:
    found: dict[str, Any] | None = await reports.by_pdf_hash(
        ctx.svc.db, await _hash_of(request, ctx.svc.settings.verify_max_bytes))
    if found is None or found["status"] not in ("final", "superseded"):
        return VerifyOut(match=False)
    return VerifyOut(
        match=True, number=found["number"], version=found["version"], status=found["status"],
        finalized_at=found["finalized_at"])
