"""Client report bodies (PRD CRP-1 to CRP-5; TRD 3.2). Requests forbid unknown fields."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from mms_common.auth import User
from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.requests.schemas import AttachmentOut, PersonRef
from app.domain import client_reports as rules

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Kind = Literal["pdf", "form"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Observation(In):
    station_id: Id
    text: Annotated[str, Field(max_length=rules.MAX_OBSERVATION * 2)]


class ClientReportIn(In):
    """CRP-1. `id` is made on the device: sending it again returns the draft already made. The
    stations default to all of the request's."""

    id: Id | None = None
    request_id: Id
    kind: Kind
    title: Annotated[str, Field(max_length=rules.MAX_TITLE * 2)] = ""
    report_date: date | None = None
    station_ids: list[Id] = Field(default_factory=list, max_length=100)


class ClientReportPatch(In):
    """CRP-2. Only what is sent changes; `version` is the one the page was looking at. A PDF
    report takes `media_id`; a form report takes the text fields and `image_ids` (pictures
    uploaded for `client_report:<id>`). Sending `media_id: null` takes the PDF off the draft."""

    version: int = Field(ge=1)
    title: Annotated[str, Field(max_length=rules.MAX_TITLE * 2)] | None = None
    report_date: date | None = None
    station_ids: list[Id] | None = Field(default=None, max_length=100)
    media_id: Id | None = None
    summary: Annotated[str, Field(max_length=rules.MAX_SUMMARY * 2)] | None = None
    observations: list[Observation] | None = Field(default=None, max_length=100)
    data_quality_notes: Annotated[str, Field(max_length=rules.MAX_NOTES * 2)] | None = None
    image_ids: list[Id] | None = Field(default=None, max_length=rules.MAX_IMAGES * 2)


class FormOut(BaseModel):
    summary: str
    observations: list[dict[str, str]]
    data_quality_notes: str
    images: list[AttachmentOut]


class ClientReportOut(BaseModel):
    id: str
    request_id: str
    request_ref: str
    kind: Kind
    status: Literal["draft", "submitted"]
    title: str
    report_date: date
    station_ids: list[str]
    file: AttachmentOut | None  # a PDF report's file
    form: FormOut
    # A form report's PDF: `none` (a PDF report, or a draft), `rendering`, `ready`, `failed`.
    # `report_id` is the report service's record, which serves the PDF once `ready`.
    render: str
    report_id: str | None
    submitted_by: PersonRef | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    can_edit: bool  # the author, while it is a draft (CRP-4)

    @classmethod
    def of(cls, doc: dict[str, Any], viewer: User) -> ClientReportOut:
        form = doc["form"]
        submitter = (
            PersonRef(id=doc["submitted_by"], name=doc["submitted_by_name"])
            if doc.get("submitted_by") else None
        )
        return cls(
            id=doc["_id"], request_id=doc["request_id"], request_ref=doc["request_ref"],
            kind=doc["kind"], status=doc["status"], title=doc["title"],
            report_date=date.fromisoformat(doc["report_date"]),
            station_ids=list(doc["station_ids"]),
            file=AttachmentOut(**doc["file"]) if doc.get("file") else None,
            form=FormOut(
                summary=form["summary"], observations=list(form["observations"]),
                data_quality_notes=form["data_quality_notes"],
                images=[AttachmentOut(**i) for i in form["images"]],
            ),
            render=doc["render"], report_id=doc.get("report_id"), submitted_by=submitter,
            submitted_at=doc.get("submitted_at"), created_at=doc["created_at"],
            updated_at=doc["updated_at"], version=doc["version"],
            can_edit=rules.can_edit(doc, viewer.id),
        )


class ClientReportPage(BaseModel):
    items: list[ClientReportOut]
