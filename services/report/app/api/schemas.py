"""Request and response bodies (extra fields are refused)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field

from app.domain.labels import MAX_STATIONS, JobStatus, JobType

StationId = Annotated[str, Field(pattern=UUID7_PATTERN)]


class LabelsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_ids: list[StationId] = Field(min_length=1, max_length=MAX_STATIONS)
    contact_phone: str | None = Field(
        default=None, max_length=30,
        description="Printed on every label. Empty uses the organization's default.",
    )


class JobResult(BaseModel):
    pages: int
    stations: int
    missing: list[str]  # requested stations that don't exist
    pdf_sha256: str
    pdf_bytes: int
    download_url: str | None = None
    expires_at: datetime | None = None


class JobOut(BaseModel):
    id: str
    type: JobType
    status: JobStatus
    error: str | None = None
    result: JobResult | None = None
    created_at: datetime
    finished_at: datetime | None = None
