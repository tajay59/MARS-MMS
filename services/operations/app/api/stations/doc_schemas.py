"""Documents and configuration versions: request and response bodies (extra fields refused).

Clients get the same document shape with the staff-only fields emptied: the media ID (they
download through the document) and who uploaded it is shown by name only (decision D4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mms_common.auth import User
from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Language = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")]
Scope = Literal["model", "station"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Documents ----------------------------------------------------------------------------------


class DocumentIn(In):
    """Made on the device or form with its own ID, so a retry creates nothing twice."""

    id: Id
    scope: Scope
    scope_id: Id
    doc_type: Annotated[str, StringConstraints(max_length=30)]
    title: Title
    version_label: Short | None = None
    language: Language | None = None
    description: Long | None = None
    client_visible: bool = False  # staff-only until someone says otherwise (DOC-4, Q7)
    media_id: Id
    supersedes_id: Id | None = None  # the version this one replaces


class DocumentPatch(In):
    version: int = Field(ge=1)
    doc_type: Annotated[str, StringConstraints(max_length=30)] | None = None
    title: Title | None = None
    version_label: Short | None = None
    language: Language | None = None
    description: Long | None = None
    client_visible: bool | None = None


class DocumentOut(BaseModel):
    id: str
    scope: str
    scope_id: str
    doc_type: str
    title: str
    version_label: str | None
    language: str | None
    description: str | None
    client_visible: bool
    media_id: str | None  # staff only
    filename: str
    size_bytes: int
    supersedes_id: str | None
    is_current: bool
    status: str
    scan_status: str | None
    uploaded_by: str | None  # a name, never an email (D4)
    created_at: datetime
    version: int

    @classmethod
    def of(cls, doc: dict[str, Any], viewer: User) -> DocumentOut:
        return cls(
            id=doc["_id"], scope=doc["scope"], scope_id=doc["scope_id"],
            doc_type=doc["doc_type"], title=doc["title"], version_label=doc.get("version_label"),
            language=doc.get("language"), description=doc.get("description"),
            client_visible=bool(doc["client_visible"]),
            media_id=None if viewer.is_client else doc["media_id"],
            filename=doc["filename"], size_bytes=doc["size_bytes"],
            supersedes_id=None if viewer.is_client else doc.get("supersedes_id"),
            is_current=bool(doc["is_current"]), status=doc["status"],
            scan_status=doc.get("scan_status"), uploaded_by=doc.get("created_by_name"),
            created_at=doc["created_at"], version=doc["version"],
        )


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    next_after: str | None = None


class ModelDocuments(BaseModel):
    model_id: str
    manufacturer: str
    model: str
    documents: list[DocumentOut]


class StationDocuments(BaseModel):
    """What the station page's Documents tab shows: the station's own and its sensors'."""

    station: list[DocumentOut]
    models: list[ModelDocuments]


class DownloadOut(BaseModel):
    """A link that works for ten minutes; it is never cached."""

    url: str
    expires_at: datetime
    filename: str


# --- Configuration versions -------------------------------------------------------------------


class ConfigFileIn(In):
    media_id: Id


class ConfigVersionIn(In):
    id: Id
    files: Annotated[list[ConfigFileIn], Field(min_length=1, max_length=50)]
    notes: Long | None = None
    visit_id: Id | None = None


class ConfigFileOut(BaseModel):
    media_id: str
    filename: str
    sha256: str
    size_bytes: int


class ConfigVersionOut(BaseModel):
    id: str
    station_id: str
    version: int
    files: list[ConfigFileOut]
    notes: str | None
    visit_id: str | None
    created_by: str | None
    created_at: datetime

    @classmethod
    def of(cls, doc: dict[str, Any]) -> ConfigVersionOut:
        return cls(
            id=doc["_id"], station_id=doc["station_id"], version=doc["version"],
            files=[ConfigFileOut(**f) for f in doc["files"]], notes=doc.get("notes"),
            visit_id=doc.get("visit_id"), created_by=doc.get("created_by_name"),
            created_at=doc["created_at"],
        )


class ConfigDiff(BaseModel):
    """CFG-3: which files differ between two versions, by name and checksum."""

    version: int
    against: int | None
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]
