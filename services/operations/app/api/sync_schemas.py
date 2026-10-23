"""Bodies for `POST /api/v1/sync` (TRD §7.2, §7.3; W14-1 to W14-4).

An operation is an envelope (`op_id`, payload version `v`, `type`, `visit_id`) and a payload that
is the body of the route that does the work, plus the station and element it is about. The
envelope is checked for the whole request; each payload is checked when its operation runs, so
one bad operation is one answer and not a refused batch.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.visits.element_schemas import ElementIn, ElementMediaIn, ElementPut, Id, In
from app.api.visits.schemas import AtIn, EndIn
from app.domain.sync import MAX_OPS

OpType = Literal[
    "visit.start", "station.arrive", "station.depart", "visit.end",
    "element.create", "element.update", "element.delete",
    "element.media_add", "element.media_remove",
]


class OpIn(In):
    op_id: Id
    v: int = Field(ge=0, le=1_000_000)
    type: str = Field(max_length=40)
    visit_id: Id
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncIn(In):
    device_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    ops: list[OpIn] = Field(max_length=MAX_OPS)


# --- Payloads: the body of the route, plus where it applies --------------------------------------


class StationAt(AtIn):
    model_config = ConfigDict(extra="forbid")
    station_id: Id


class CreatePayload(ElementIn):
    station_id: Id


class UpdatePayload(ElementPut):
    station_id: Id
    element_id: Id


class DeletePayload(In):
    station_id: Id
    element_id: Id
    base_version: int = Field(ge=1)


class MediaAddPayload(ElementMediaIn):
    station_id: Id
    element_id: Id


class MediaRemovePayload(In):
    station_id: Id
    element_id: Id
    media_id: Id


class StartPayload(AtIn):
    model_config = ConfigDict(extra="forbid")


class EndPayload(EndIn):
    model_config = ConfigDict(extra="forbid")


# --- Answers -------------------------------------------------------------------------------------


class AnswerOut(BaseModel):
    op_id: str
    status: Literal["applied", "duplicate", "conflict", "error", "skipped"]
    code: str | None = None
    message: str | None = None
    retryable: bool = False
    # The server's copy of an element that changed under the phone (status `conflict`)
    current: dict[str, Any] | None = None
    # What the operation made: the element or the visit as the server holds it now
    result: dict[str, Any] | None = None


class SyncOut(BaseModel):
    answers: list[AnswerOut]
