"""Requests module request and response bodies. Requests forbid unknown fields.

Clients and staff get the same shapes: a request holds no staff-only fields yet (internal
comments arrive with comments, W9). Staff names are shown to clients (decision D4); email and
phone never are.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mms_common.auth import User
from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.visits.schemas import VisitBrief
from app.domain.requests import comments as comment_rules
from app.domain.requests import rules

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                         max_length=rules.MAX_TITLE)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                               max_length=rules.MAX_DESCRIPTION)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Category = Literal[
    "fault", "communications", "power", "calibration", "relocation", "inspection", "other",
]
Priority = Literal["low", "normal", "high", "urgent"]
RequestStatus = Literal[
    "submitted", "approved", "denied", "assigned", "scheduled", "in_progress", "client_review",
    "reopened", "closed", "cancelled",
]
Action = Literal[
    "approve", "deny", "assign", "claim", "release", "cancel", "edit", "schedule_visit",
    "accept", "reject",
]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestIn(In):
    """REQ-1, REQ-2. `id` is made on the device (rule 9): sending the same one again returns
    the request already made instead of a second one. An admin names the `org_id` (every
    station must be that organization's); a client's is their own."""

    id: Id | None = None
    org_id: Id | None = None
    title: Title
    description: Description
    category: Category
    priority: Priority = "normal"
    station_ids: list[Id] = Field(min_length=1, max_length=rules.MAX_STATIONS)
    # PDFs uploaded for `request:<id>` before the request exists, so `id` is needed with them
    media_ids: list[Id] = Field(default_factory=list, max_length=comment_rules.MAX_ATTACHMENTS)


class CommentIn(In):
    """REQ-9, REQ-10. `id` is made on the device: sending it again returns the comment already
    posted. Files are PDFs uploaded for `comment:<request id>:<id>` and already checked."""

    id: Id | None = None
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                           max_length=comment_rules.MAX_BODY)]
    internal: bool = False
    media_ids: list[Id] = Field(default_factory=list, max_length=comment_rules.MAX_ATTACHMENTS)


class CommentPatch(In):
    """Change a comment within 15 minutes: its text, and for staff whether it is internal."""

    version: int = Field(ge=1)
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                           max_length=comment_rules.MAX_BODY)] | None = None
    internal: bool | None = None


class RequestPatch(In):
    """REQ-11. Only what is sent changes. `version` is the one the editor was looking at."""

    version: int = Field(ge=1)
    title: Title | None = None
    description: Description | None = None
    category: Category | None = None
    priority: Priority | None = None
    station_ids: list[Id] | None = Field(default=None, min_length=1, max_length=rules.MAX_STATIONS)


class DenyIn(In):
    reason: Reason  # the client sees it (REQ-6)


class AcceptIn(In):
    """REQ-13, W18-2/3. The client signs the work off. `reviewing` is the request's
    `review_started_at` as the page read it (not the milestone, which keeps the first). `image`
    is the drawing as base64 PNG (a `data:image/png;base64,` URI is accepted), also for "use my
    typed name"."""

    reviewing: datetime
    typed_name: str = Field(max_length=400)
    image: str = Field(max_length=300_000)
    attestation_accepted: Literal[True]
    comment: Reason | None = None


class RejectIn(In):
    """REQ-13. The client sends the work back, with a reason the staff are told."""

    reviewing: datetime
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5,
                                             max_length=1000)]


class CancelIn(In):
    reason: Reason | None = None  # required from Scheduled on (REQ-11)


class AssignIn(In):
    """REQ-7. The people the request is put with; `version` guards a change of staff on a request
    that is already Assigned against a second admin doing the same."""

    staff_ids: list[Id] = Field(min_length=1, max_length=10)
    version: int | None = Field(default=None, ge=1)


class RequestStation(BaseModel):
    id: str
    code: str
    name: str
    country: str


class PersonRef(BaseModel):
    id: str
    name: str


class AttachmentOut(BaseModel):
    media_id: str
    name: str
    size_bytes: int


class CommentOut(BaseModel):
    id: str
    request_id: str
    author: PersonRef
    author_role: str
    body: str
    internal: bool
    attachments: list[AttachmentOut]
    created_at: datetime
    edited_at: datetime | None
    version: int
    # When the author can no longer change it; null for everyone else (and once it has passed)
    editable_until: datetime | None

    @classmethod
    def of(cls, doc: dict[str, Any], viewer: User, now: datetime) -> CommentOut:
        until = doc["created_at"] + comment_rules.EDIT_WINDOW
        mine = doc["author_id"] == viewer.id and now <= until
        return cls(
            id=doc["_id"], request_id=doc["request_id"],
            author=PersonRef(id=doc["author_id"], name=doc["author_name"]),
            author_role=doc["author_role"], body=doc["body"], internal=bool(doc["internal"]),
            attachments=[AttachmentOut(**a) for a in doc["attachments"]],
            created_at=doc["created_at"], edited_at=doc.get("edited_at"), version=doc["version"],
            editable_until=until if mine else None,
        )


class CommentPage(BaseModel):
    items: list[CommentOut]


class HistoryEntry(BaseModel):
    from_status: str | None
    to_status: str
    at: datetime
    by: PersonRef | None
    note: str | None


class RequestSummary(BaseModel):
    """A row of the request list (AFD `/requests`)."""

    id: str
    ref: str
    title: str
    category: str
    priority: str
    status: str
    org_id: str
    org_name: str | None
    stations: list[RequestStation]
    requested_by: PersonRef | None
    assigned_staff: list[PersonRef]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(
        cls, doc: dict[str, Any], stations: dict[str, dict[str, Any]], orgs: dict[str, str],
    ) -> RequestSummary:
        found = [stations[i] for i in doc["station_ids"] if i in stations]
        return cls(
            id=doc["_id"], ref=doc["ref"], title=doc["title"], category=doc["category"],
            priority=doc["priority"], status=doc["status"], org_id=doc["org_id"],
            org_name=orgs.get(doc["org_id"]),
            stations=[RequestStation(id=s["_id"], code=s["code"], name=s["name"],
                                 country=s["country"]) for s in found],
            requested_by=PersonRef(id=doc["created_by"], name=doc["requester_name"])
            if doc.get("created_by") else None,
            assigned_staff=[PersonRef(id=i, name=n) for i, n in doc.get("assigned_staff", [])],
            created_at=doc["created_at"], updated_at=doc["updated_at"],
        )


class Milestones(BaseModel):
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    assigned_at: datetime | None = None
    first_visit_at: datetime | None = None
    review_started_at: datetime | None = None
    closed_at: datetime | None = None


class VerificationOut(BaseModel):
    """The client's answer to Client Review (REQ-13). The drawn signature is not in it."""

    outcome: Literal["accepted", "rejected", "auto_closed"]
    by: PersonRef | None
    at: datetime
    comment: str | None
    typed_name: str | None

    @classmethod
    def of(cls, doc: dict[str, Any] | None) -> VerificationOut | None:
        if not doc:
            return None
        by = PersonRef(id=doc["by"], name=doc.get("by_name") or "") if doc.get("by") else None
        return cls(
            outcome=doc["outcome"], by=by, at=doc["at"], comment=doc.get("comment"),
            typed_name=(doc.get("signature") or {}).get("typed_name"),
        )


class RequestDetail(RequestSummary):
    description: str
    status_history: list[HistoryEntry]
    denial_reason: str | None
    cancel_reason: str | None
    milestones: Milestones
    version: int
    actions: list[Action]  # what the person asking may do now (viewers: none)
    attachments: list[AttachmentOut]
    comment_count: int  # as this reader may see them: a client's count leaves out internal ones
    visits: list[VisitBrief]  # soonest first (PRD VIS-11: a client sees their own organization's)
    verification: VerificationOut | None  # the client's last answer to Client Review
    review_started_at: datetime | None  # the current review's start: what `reviewing` names
    auto_close_at: datetime | None  # while in Client Review: when it closes if nobody answers

    @classmethod
    def build(
        cls, doc: dict[str, Any], stations: dict[str, dict[str, Any]], orgs: dict[str, str],
        actions: list[Action], comment_count: int = 0, visits: list[VisitBrief] | None = None,
        auto_close_at: datetime | None = None,
    ) -> RequestDetail:
        return cls(
            **RequestSummary.of(doc, stations, orgs).model_dump(),
            description=doc["description"],
            status_history=[
                HistoryEntry(
                    from_status=h.get("from"), to_status=h["to"], at=h["at"],
                    by=PersonRef(id=h["by"], name=h.get("by_name") or "") if h.get("by") else None,
                    note=h.get("note"),
                )
                for h in doc["status_history"]
            ],
            denial_reason=doc.get("denial_reason"), cancel_reason=doc.get("cancel_reason"),
            milestones=Milestones(**doc.get("milestones", {})), version=doc["version"],
            actions=actions, attachments=[AttachmentOut(**a) for a in doc.get("attachments", [])],
            comment_count=comment_count, visits=visits or [],
            verification=VerificationOut.of(doc.get("client_verification")),
            review_started_at=doc.get("review_started_at"), auto_close_at=auto_close_at,
        )


class QueueItem(RequestSummary):
    """A row of the queue: a request and how long it has waited."""

    approved_at: datetime | None

    @classmethod
    def waiting(
        cls, doc: dict[str, Any], stations: dict[str, dict[str, Any]], orgs: dict[str, str],
    ) -> QueueItem:
        return cls(
            **RequestSummary.of(doc, stations, orgs).model_dump(),
            approved_at=doc.get("milestones", {}).get("approved_at"),
        )


class QueuePage(BaseModel):
    items: list[QueueItem]
    total: int


class Workload(BaseModel):
    """Open requests per person (staff IDs not listed have none)."""

    open_requests: dict[str, int]


class RequestPage(BaseModel):
    items: list[RequestSummary]
    total: int
    next_after: str | None

