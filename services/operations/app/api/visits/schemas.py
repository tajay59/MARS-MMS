"""Visits module request and response bodies (TRD §3.2 visits; PRD VIS-1 to VIS-4, VIS-9, VIS-11).

Staff and clients get one shape, filtered when it is built (rule 6): a client never gets the
scheduling `notes`, and a station's board summary counts only what a client may see (the shared
elements of an ended visit, W11-28). The board itself is read from its own routes.
Staff names are shown to clients (decisions A7, D4); email and phone never are.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from mms_common.auth import User
from mms_common.ids import UUID7_PATTERN
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.api.visits.element_schemas import BoardSummaryOut
from app.domain.visits import actions as visit_actions
from app.domain.visits import schedule
from app.domain.visits.elements import Summary, summarize

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Notes = Annotated[str, StringConstraints(max_length=schedule.MAX_NOTES)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
VisitStatus = Literal["planned", "started", "ended", "cancelled"]
VisitAction = Literal["reschedule", "cancel", "start", "end", "change_owner", "restore"]
StationAction = Literal["arrive", "depart"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisitStationIn(In):
    station_id: Id
    owner_staff_id: Id | None = None  # the lead when absent


class VisitIn(In):
    """Scheduling (VIS-1). `id` is made on the device and makes a retry safe (rule 9): the same
    `id` again returns the visit that was made."""

    id: Id | None = None
    request_id: Id
    planned_start: AwareDatetime
    planned_end: AwareDatetime
    staff_ids: list[Id] = Field(min_length=1, max_length=schedule.MAX_STAFF)
    lead_staff_id: Id | None = None
    stations: list[VisitStationIn] = Field(min_length=1, max_length=schedule.MAX_STATIONS)
    notes: Notes | None = None


class VisitPatch(In):
    """A planned visit: any of these. A started visit: only `stations[].owner_staff_id`. What is
    left out stays as it is; `notes: null` clears the notes."""

    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    staff_ids: list[Id] | None = Field(default=None, min_length=1, max_length=schedule.MAX_STAFF)
    lead_staff_id: Id | None = None
    stations: list[VisitStationIn] | None = Field(
        default=None, min_length=1, max_length=schedule.MAX_STATIONS
    )
    notes: Notes | None = None
    version: int | None = None  # the editor's stale-write check


class AtIn(In):
    """The time something happened, as the device saw it. The server's now when absent."""

    at: AwareDatetime | None = None


class VisitCancelIn(In):
    reason: Reason | None = None


class EndIn(In):
    additional_visit_required: bool
    follow_up_notes: Notes | None = None
    at: AwareDatetime | None = None


class VisitPersonOut(BaseModel):
    id: str
    name: str


class VisitStationOut(BaseModel):
    station_id: str
    station_code: str | None
    station_name: str | None
    time_zone: str | None
    owner: VisitPersonOut
    arrived_at: datetime | None
    departed_at: datetime | None
    actions: list[StationAction]  # what the person asking may do here now
    board: BoardSummaryOut  # the station's board at a glance (W11-18)


class VisitBrief(BaseModel):
    """A visit as the request page lists it."""

    id: str
    ref: str
    status: VisitStatus
    planned_start: datetime
    planned_end: datetime
    lead: VisitPersonOut

    @classmethod
    def of(cls, doc: dict[str, Any]) -> VisitBrief:
        return cls(
            id=doc["_id"], ref=doc["ref"], status=doc["status"],
            planned_start=doc["planned_start"], planned_end=doc["planned_end"],
            lead=_person(doc, doc["lead_staff_id"]),
        )


class PreparedOn(BaseModel):
    """A phone this visit is prepared on (W13-9): who, and when. Staff only."""

    user: VisitPersonOut
    at: datetime


class VisitOut(VisitBrief):
    request_id: str
    request_ref: str | None
    request_title: str | None
    org_id: str
    started_at: datetime | None
    ended_at: datetime | None
    additional_visit_required: bool | None
    follow_up_notes: str | None
    notes: str | None  # staff only
    staff: list[VisitPersonOut]
    stations: list[VisitStationOut]
    actions: list[VisitAction]
    prepared_on: list[PreparedOn]  # staff only; empty for a client
    version: int

    @classmethod
    def build(
        cls, doc: dict[str, Any], request: dict[str, Any] | None, viewer: User,
        boards: Mapping[str, Summary] | None = None,
    ) -> VisitOut:
        """`boards` is each station's summary, by station (an empty board when absent)."""
        staff_side = not viewer.is_client and (viewer.is_admin or "technician" in viewer.roles)
        assigned = list(request.get("assigned_staff_ids", [])) if request else []
        acts = (visit_actions.visit_actions(doc, viewer.id, viewer.is_admin, assigned)
                if staff_side else [])
        return cls(
            **VisitBrief.of(doc).model_dump(),
            request_id=doc["request_id"],
            request_ref=request["ref"] if request else None,
            request_title=request.get("title") if request else None,
            org_id=doc["org_id"], started_at=doc.get("started_at"), ended_at=doc.get("ended_at"),
            additional_visit_required=doc.get("additional_visit_required"),
            follow_up_notes=doc.get("follow_up_notes"),
            notes=None if viewer.is_client else doc.get("notes"),
            staff=[_person(doc, i) for i in doc["staff_ids"]],
            stations=[
                VisitStationOut(
                    station_id=s["station_id"], station_code=s.get("station_code"),
                    station_name=s.get("station_name"), time_zone=s.get("time_zone"),
                    owner=_person(doc, s["owner_staff_id"]), arrived_at=s.get("arrived_at"),
                    departed_at=s.get("departed_at"),
                    actions=cast(list[StationAction], visit_actions.station_actions(
                        doc, s, viewer.id, viewer.is_admin) if staff_side else []),
                    board=BoardSummaryOut.of(
                        (boards or {}).get(s["station_id"]) or summarize([])),
                )
                for s in doc["stations"]
            ],
            actions=cast(list[VisitAction], acts),
            prepared_on=[] if viewer.is_client else [
                PreparedOn(user=VisitPersonOut(id=p["user_id"], name=p.get("user_name", "")),
                           at=p["at"])
                for p in doc.get("prepared_on", [])
            ],
            version=doc["version"],
        )


def _person(doc: dict[str, Any], staff_id: str) -> VisitPersonOut:
    for entry in doc.get("staff", []):
        if entry["id"] == staff_id:
            return VisitPersonOut(id=staff_id, name=entry["name"])
    return VisitPersonOut(id=staff_id, name="")


class StaffOut(BaseModel):
    """Someone who may attend a visit: a name and roles, never an email or phone."""

    id: str
    name: str
    roles: list[str]


class StaffList(BaseModel):
    items: list[StaffOut]


class VisitPage(BaseModel):
    items: list[VisitOut]
    total: int
    next_after: str | None
