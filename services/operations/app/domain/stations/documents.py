"""Documents and configuration versions (PRD DOC-1 to DOC-4, CFG-1 to CFG-3; TRD §3.2, §5.2).
No I/O here.

A document is a row that points at a file in the media service. The row is created as soon
as the upload is whole and stays `pending` until media says the file passed its checks, so a
file nobody has scanned is never offered for download. A configuration version is a set of
files that can never change, so it takes only files that have already passed (`ready`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from mms_common.errors import Conflict, ValidationFailed

DOCUMENT_KINDS = frozenset({"pdf", "document"})  # media kinds a document may hold
CONFIG_KINDS = frozenset({"config"})
CERTIFICATE_KINDS = frozenset({"pdf", "document"})
# Where a file is on its way: attachable once it is whole, whatever checks are left.
ARRIVED = frozenset({"uploaded", "processing", "ready"})
MAX_CONFIG_FILES = 50


class Scope(StrEnum):
    MODEL = "model"  # a sensor model: shows on every station using it (DOC-1)
    STATION = "station"  # one station (DOC-2)


class DocStatus(StrEnum):
    PENDING = "pending"  # the file is whole; media's checks are not finished
    AVAILABLE = "available"  # clean, and downloadable
    FAILED = "failed"  # the file did not pass; upload a new one


DOC_TYPES: dict[Scope, tuple[str, ...]] = {
    Scope.MODEL: ("datasheet", "operations_manual", "maintenance_manual", "other"),
    Scope.STATION: ("installation", "site_drawing", "other"),
}


def check_doc_type(scope: Scope, doc_type: str) -> str:
    if doc_type not in DOC_TYPES[scope]:
        raise ValidationFailed(
            f"A {scope.value} document can be: {', '.join(DOC_TYPES[scope])}",
            code="bad_doc_type", field="doc_type",
        )
    return doc_type


def owner_ref(scope: Scope, scope_id: str) -> str:
    """The reference media files an upload under (TRD §5.3)."""
    return f"document:{scope.value}:{scope_id}"


def config_owner_ref(station_id: str) -> str:
    return f"config:{station_id}"


def certificate_owner_ref(unit_id: str) -> str:
    return f"calibration:{unit_id}"


@dataclass(frozen=True)
class FileFacts:
    """What media says about a file, reduced to what the rules need."""

    owner_ref: str
    kind: str
    status: str
    uploaded_by: str
    filename: str
    size_bytes: int
    checksum_sha256: str
    scan_status: str | None = None


def check_file(
    facts: FileFacts | None, *, owner: str, kinds: frozenset[str], user_id: str,
    ready_only: bool = False, field: str = "media_id",
) -> FileFacts:
    """A file may be attached by the person who uploaded it, to the owner it was uploaded
    for, if it has arrived. Anything else is refused with a reason a form can show."""
    if facts is None:
        raise ValidationFailed("That file wasn't found", code="unknown_file", field=field)
    if facts.owner_ref != owner:
        raise ValidationFailed("That file was uploaded for something else", code="wrong_owner",
                               field=field)
    if facts.uploaded_by != user_id:
        raise ValidationFailed("That file was uploaded by someone else", code="not_yours",
                               field=field)
    if facts.kind not in kinds:
        raise ValidationFailed("That kind of file can't be used here", code="wrong_kind",
                               field=field)
    if ready_only:
        if facts.status != "ready":
            raise Conflict("The file is still being checked. Try again in a moment",
                           reason="file_not_ready", media_id=field)
    elif facts.status not in ARRIVED:
        raise ValidationFailed("The upload didn't finish", code="file_not_uploaded", field=field)
    return facts


def status_for(file_status: str) -> DocStatus:
    """A file that has already passed is available at once; any other waits for media."""
    return DocStatus.AVAILABLE if file_status == "ready" else DocStatus.PENDING


# --- Configuration versions -----------------------------------------------------------------


def check_unique_names(files: list[FileFacts]) -> None:
    seen: set[str] = set()
    for f in files:
        key = f.filename.casefold()
        if key in seen:
            raise ValidationFailed(f"Two files are called {f.filename}", code="duplicate_filename",
                                   field="files")
        seen.add(key)


@dataclass(frozen=True)
class Diff:
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]


def diff_files(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> Diff:
    """File-level difference between two versions, by name and checksum (CFG-3)."""
    before = {f["filename"]: f["sha256"] for f in old}
    after = {f["filename"]: f["sha256"] for f in new}
    return Diff(
        added=sorted(n for n in after if n not in before),
        removed=sorted(n for n in before if n not in after),
        changed=sorted(n for n in after if n in before and after[n] != before[n]),
        unchanged=sorted(n for n in after if n in before and after[n] == before[n]),
    )
