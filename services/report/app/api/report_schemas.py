"""Bodies of the visit report routes (TRD 3.4). Staff-side shapes: a client gets no draft."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PdfState(BaseModel):
    """Where the draft PDF stands. `current` is false when the report has changed since it was
    drawn: a preview draws it again."""

    state: str  # none | rendering | ready | failed
    current: bool
    pages: int | None = None
    rendered_at: datetime | None = None
    error: str | None = None


class ReportSummary(BaseModel):
    id: str
    type: str
    subject_ref: str
    visit_id: str | None = None
    request_id: str
    number: str
    version: int
    status: str
    pdf: PdfState
    awaiting_media: int
    drafted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReportOut(ReportSummary):
    content_version: int
    facts_version: int
    content: dict[str, Any]


class PreviewOut(BaseModel):
    """`ready`: the PDF for the report as it is now exists. `rendering`: poll the report."""

    state: str
    pdf: PdfState


class DownloadOut(BaseModel):
    url: str
    expires_at: datetime
    filename: str
    current: bool
