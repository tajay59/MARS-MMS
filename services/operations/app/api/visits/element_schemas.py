"""Bodies for a station's board (TRD §3.2.3; PRD VIS-5, VIS-7; W11-20 to W11-28).

Staff and clients get one shape, filtered when it is built (rule 6): a client sees only shared
elements of an ended visit (the repository and the route make sure of that), never a file a staff
member hid, and authors by name only (D4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mms_common.auth import User
from mms_common.ids import UUID7_PATTERN
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.domain.visits import elements as rules

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Kind = Literal["note", "task", "recommendation", "config"]
Section = Literal["main", "before", "after"]
Priority = Literal["low", "medium", "high"]
# The rules check the lengths after trimming; these bounds stop an absurd body early
Title = Annotated[str, StringConstraints(max_length=rules.MAX_TITLE * 2)]
Description = Annotated[str, StringConstraints(max_length=rules.MAX_DESCRIPTION * 2)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemBody(In):
    id: Id  # made on the device, so a retried save never doubles an item
    text: Annotated[str, StringConstraints(max_length=rules.MAX_ITEM * 2)]
    done: bool = False


class ElementIn(In):
    """A new element. `id` is made on the device (rule 9): the same `id` and content again
    returns the element that was made."""

    id: Id
    kind: Kind
    title: Title
    description: Description | None = None
    items: list[ItemBody] = Field(default_factory=list, max_length=rules.MAX_ITEMS * 2)
    priority: Priority | None = None
    shared: bool | None = None  # the kind's default when absent (W11-28)
    device_id: Annotated[str, StringConstraints(max_length=64)] | None = None


class ElementPut(In):
    """The whole editable content, with the version the editor was looking at (W11-26)."""

    title: Title
    description: Description | None = None
    items: list[ItemBody] = Field(default_factory=list, max_length=rules.MAX_ITEMS * 2)
    priority: Priority | None = None
    shared: bool
    base_version: int = Field(ge=1)
    device_id: Annotated[str, StringConstraints(max_length=64)] | None = None


class ElementMediaIn(In):
    """Put an uploaded file on a section of the element. `media_id` is the upload's own id, so a
    retry attaches nothing twice."""

    media_id: Id
    section: Section
    caption: str | None = None
    captured_at: AwareDatetime | None = None


class ElementMediaPatch(In):
    """Any of these. `caption: null` clears it; `hidden: true` keeps the file from the client."""

    caption: str | None = None
    hidden: bool | None = None


class PersonOut(BaseModel):
    id: str
    name: str


class ItemOut(BaseModel):
    id: str
    text: str
    done: bool
    done_by: str | None
    done_at: datetime | None


class ElementMediaOut(BaseModel):
    """A file on the element. Its thumbnail, link and processing state come from the media
    service by `media_id`, so nothing here expires."""

    media_id: str
    kind: Literal["image", "video", "config"]
    filename: str
    size_bytes: int | None
    caption: str | None
    captured_at: datetime | None
    added_by: PersonOut
    added_at: datetime
    hidden: bool  # kept from the client even when the element is shared


class RequestRefOut(BaseModel):
    id: str
    ref: str


class ElementOut(BaseModel):
    id: str
    visit_id: str
    station_id: str
    kind: Kind
    title: str
    description: str | None
    items: list[ItemOut]
    complete: bool | None  # a task's
    completed_at: datetime | None
    priority: Priority | None
    request_ref: RequestRefOut | None
    config_version_ids: list[str]
    media: dict[str, list[ElementMediaOut]]  # by section: `main`, or `before` and `after`
    shared: bool
    created_by: PersonOut
    created_at: datetime
    updated_at: datetime
    version: int
    can_edit: bool  # whether the person asking may change it now

    @classmethod
    def build(
        cls, doc: dict[str, Any], station: dict[str, Any], viewer: User, *, open_: bool
    ) -> ElementOut:
        client = viewer.is_client
        items = doc.get("items", [])
        return cls(
            id=doc["_id"], visit_id=doc["visit_id"], station_id=doc["station_id"],
            kind=doc["kind"], title=doc["title"], description=doc.get("description"),
            items=[ItemOut(id=i["id"], text=i["text"], done=i["done"], done_by=i.get("done_by"),
                           done_at=i.get("done_at")) for i in items],
            complete=rules.is_complete(items) if doc["kind"] == "task" else None,
            completed_at=doc.get("completed_at"), priority=doc.get("priority"),
            request_ref=RequestRefOut(**doc["request_ref"]) if doc.get("request_ref") else None,
            config_version_ids=list(doc.get("config_version_ids", [])),
            media={
                section: [_media(e) for e in entries if not (client and e.get("hidden"))]
                for section, entries in doc.get("media", {}).items()
            },
            shared=bool(doc.get("shared")),
            created_by=PersonOut(id=doc["created_by"], name=doc.get("created_by_name") or ""),
            created_at=doc["created_at"], updated_at=doc["updated_at"], version=doc["version"],
            can_edit=open_ and not client and "viewer" not in viewer.roles
            and rules.can_edit(doc, station, viewer.id, viewer.is_admin),
        )


def _media(entry: dict[str, Any]) -> ElementMediaOut:
    return ElementMediaOut(
        media_id=entry["media_id"], kind=entry["kind"], filename=entry["filename"],
        size_bytes=entry.get("size_bytes"), caption=entry.get("caption"),
        captured_at=entry.get("captured_at"),
        added_by=PersonOut(id=entry["added_by"], name=entry.get("added_by_name") or ""),
        added_at=entry["added_at"], hidden=bool(entry.get("hidden")),
    )


class ElementList(BaseModel):
    items: list[ElementOut]
    can_add: bool  # whether the person asking may add an element to this board now


class BoardCover(BaseModel):
    media_id: str
    kind: Literal["image", "video"]


class BoardSummaryOut(BaseModel):
    """A station's board at a glance (the visit page, the End dialog's warning)."""

    note: int
    task: int
    recommendation: int
    config: int
    incomplete_tasks: int
    cover: BoardCover | None

    @classmethod
    def of(cls, summary: rules.Summary) -> BoardSummaryOut:
        return cls(
            **summary.counts, incomplete_tasks=summary.incomplete_tasks,
            cover=BoardCover(media_id=summary.cover[0], kind=summary.cover[1])  # type: ignore[arg-type]
            if summary.cover else None,
        )
