"""Requests module request and response bodies. Requests forbid unknown fields.

Clients and staff get the same shapes: a request holds no staff-only fields yet (internal
comments arrive with comments, W9). Staff names are shown to clients (decision D4); email and
phone never are.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
Action = Literal["approve", "deny", "assign", "cancel", "edit"]


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


class CancelIn(In):
    reason: Reason | None = None  # required from Scheduled on (REQ-11)


class StationRef(BaseModel):
    id: str
    code: str
    name: str
    country: str


class PersonRef(BaseModel):
    id: str
    name: str


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
    stations: list[StationRef]
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
            stations=[StationRef(id=s["_id"], code=s["code"], name=s["name"],
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


class RequestDetail(RequestSummary):
    description: str
    status_history: list[HistoryEntry]
    denial_reason: str | None
    cancel_reason: str | None
    milestones: Milestones
    version: int
    actions: list[Action]  # what the person asking may do now (viewers: none)

    @classmethod
    def build(
        cls, doc: dict[str, Any], stations: dict[str, dict[str, Any]], orgs: dict[str, str],
        actions: list[Action],
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
            actions=actions,
        )


class RequestPage(BaseModel):
    items: list[RequestSummary]
    total: int
    next_after: str | None

