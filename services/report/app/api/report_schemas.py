"""Bodies of the visit report routes (TRD 3.4). Staff-side shapes: a client gets no draft."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    finalized_at: datetime | None = None
    pdf_sha256: str | None = None  # the code printed in a final report's footer is its start
    created_at: datetime
    updated_at: datetime


class SignatureOut(BaseModel):
    """One signature of this version. Staff only: `image` is the drawn PNG as a data URI, and is
    absent once the signature was cleared (the record stays, W17-4)."""

    id: str
    signer_id: str
    role: str  # lead | attending
    signer_name: str
    typed_name: str
    attestation: str
    signed_at: datetime
    content_version: int
    valid: bool
    cleared_at: datetime | None = None
    cleared_by: str | None = None  # a person's id, `facts` or `reopen`
    image: str | None = None


class ReportOut(ReportSummary):
    content_version: int
    facts_version: int
    content: dict[str, Any]
    # Staff only (a client's are empty or null): who attended, what they sign, and what exists
    content_hash: str | None = None
    lead_staff_id: str | None = None
    staff_ids: list[str] = []
    attestation: str | None = None
    signatures: list[SignatureOut] = []
    finalized_by: str | None = None
    finalize_error: str | None = None  # why the last finalize stopped
    supersedes_id: str | None = None


class NarrativeStation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: str = Field(max_length=64)
    work_performed: str = Field(max_length=20_000)


class NarrativeEdit(BaseModel):
    """Fields that are given replace the old text; the others stay."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None = Field(default=None, max_length=20_000)
    recommendations: str | None = Field(default=None, max_length=20_000)
    follow_up: str | None = Field(default=None, max_length=20_000)
    stations: list[NarrativeStation] | None = Field(default=None, max_length=100)


class SelectionEdit(BaseModel):
    """A photo's place in the report: `in_body` (else the appendix) and its caption here."""

    model_config = ConfigDict(extra="forbid")

    media_id: str = Field(max_length=64)
    in_body: bool | None = None
    caption: str | None = Field(default=None, max_length=1_000)


class ContentPatch(BaseModel):
    """PATCH /reports/{id}/content (W17-2). `content_version` is the one the editor read."""

    model_config = ConfigDict(extra="forbid")

    content_version: int = Field(ge=1)
    narrative: NarrativeEdit | None = None
    media_selection: list[SelectionEdit] | None = Field(default=None, max_length=500)


class ReopenIn(BaseModel):
    """POST /reports/{id}/reopen (W17-10): why the final report is being corrected."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(max_length=2_000)


class VerifyIn(BaseModel):
    """POST /reports/verify (W17-12): the SHA-256 of a report's PDF as 64 hex characters."""

    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(pattern="^[0-9a-fA-F]{64}$")


class VerifyOut(BaseModel):
    """Whether a PDF is one this system issued. Names the report and its version; no content."""

    match: bool
    number: str | None = None
    version: int | None = None
    status: str | None = None  # final | superseded
    finalized_at: datetime | None = None


class SignIn(BaseModel):
    """POST /reports/{id}/sign (W17-6): the version the person read, the name they typed and
    the drawing as base64 PNG (a `data:image/png;base64,` URI is accepted)."""

    model_config = ConfigDict(extra="forbid")

    content_version: int = Field(ge=1)
    typed_name: str = Field(max_length=400)
    image: str = Field(max_length=300_000)


class PreviewOut(BaseModel):
    """`ready`: the PDF for the report as it is now exists. `rendering`: poll the report."""

    state: str
    pdf: PdfState


class DownloadOut(BaseModel):
    url: str
    expires_at: datetime
    filename: str
    current: bool
