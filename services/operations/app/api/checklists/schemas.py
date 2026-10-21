"""Checklist template request and response bodies (PRD VIS-8). Requests forbid unknown fields."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.checklists import templates

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemIn(In):
    id: Id | None = None  # keep it when editing, so results can point at the item
    label: str = Field(min_length=1, max_length=templates.MAX_LABEL)
    help: str | None = Field(default=None, max_length=templates.MAX_HELP)


class TemplateIn(In):
    name: str = Field(min_length=1, max_length=templates.MAX_NAME)
    station_type: str | None = Field(default=None, max_length=templates.MAX_TYPE)
    sensor_model_id: Id | None = None
    items: list[ItemIn] = Field(min_length=1, max_length=templates.MAX_ITEMS)


class TemplatePatch(In):
    """`version` is the version the editor was looking at: if someone saved a newer one, 409."""

    version: int
    name: str | None = Field(default=None, min_length=1, max_length=templates.MAX_NAME)
    items: list[ItemIn] | None = Field(default=None, min_length=1, max_length=templates.MAX_ITEMS)
    active: bool | None = None


class ItemOut(BaseModel):
    id: str
    label: str
    help: str | None


class TemplateOut(BaseModel):
    id: str  # the family: stable across versions
    name: str
    station_type: str | None
    sensor_model_id: str | None
    sensor_model_name: str | None
    version: int
    is_current: bool
    active: bool
    items: list[ItemOut]
    created_at: datetime

    @classmethod
    def of(cls, doc: dict[str, Any], model_name: str | None = None) -> TemplateOut:
        return cls(
            id=doc["family_id"], name=doc["name"], station_type=doc.get("station_type"),
            sensor_model_id=doc.get("sensor_model_id"), sensor_model_name=model_name,
            version=doc["version"], is_current=doc["is_current"], active=doc["active"],
            items=[ItemOut(id=i["id"], label=i["label"], help=i.get("help")) for i in doc["items"]],
            created_at=doc["created_at"],
        )


class TemplateList(BaseModel):
    items: list[TemplateOut]


class ResolvedItem(BaseModel):
    id: str
    label: str
    help: str | None
    group: str
    template_id: str
    template_version: int


class Resolved(BaseModel):
    """What a visit to this station is given (W10-11)."""

    station_id: str
    station_type: str | None
    items: list[ResolvedItem]
