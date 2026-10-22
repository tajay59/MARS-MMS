"""What a stored file may be (TRD §3.3, §10.2; PRD MED-3, MED-6). Pure rules: no I/O.

The documents path (Phase 2) handles `pdf`, `document` and `config`. `image` and `video` are
named here so the limits live in one place; the service enables them in Phase 4.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from urllib.parse import quote

MiB = 1024 * 1024
PART_SIZE = 8 * MiB  # S3 needs at least 5 MiB for every part but the last (TRD §10.2)


class Kind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    PDF = "pdf"
    CONFIG = "config"
    DOCUMENT = "document"


class Status(StrEnum):
    PENDING = "pending"  # the record exists; parts are still arriving
    UPLOADED = "uploaded"  # whole object stored; checks to run
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class Visibility(StrEnum):
    STAFF = "staff"  # every file starts here (ADR-19)
    ORG = "org"


class ScanStatus(StrEnum):
    CLEAN = "clean"
    SKIPPED = "skipped"  # the scanner is switched off on this host


# MED-6: 200 MB per video, 25 MB per image, 50 MB per document.
LIMITS: dict[Kind, int] = {
    Kind.VIDEO: 200 * MiB,
    Kind.IMAGE: 25 * MiB,
    Kind.PDF: 50 * MiB,
    Kind.DOCUMENT: 50 * MiB,
    Kind.CONFIG: 50 * MiB,
}

TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.PENDING: frozenset({Status.UPLOADED, Status.FAILED, Status.DELETED}),
    Status.UPLOADED: frozenset({Status.PROCESSING, Status.FAILED, Status.DELETED}),
    Status.PROCESSING: frozenset({Status.READY, Status.FAILED, Status.UPLOADED}),
    Status.READY: frozenset({Status.DELETED}),
    Status.FAILED: frozenset({Status.DELETED}),
    Status.DELETED: frozenset(),
}


def can_move(old: Status, new: Status) -> bool:
    return new in TRANSITIONS[old]


class Rejected(ValueError):
    """The upload breaks a rule. `code` is stable for clients; the message is for people."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- Names and types ---------------------------------------------------------------------------

DOCUMENT_TYPES: dict[str, str] = {  # extension -> Content-Type served on download
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
# Photos and video from phones (PRD MED-1, MED-2). What arrives is checked by name and by its first
# bytes; what is shown is the processed copy, never the original.
IMAGE_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif",
}
VIDEO_TYPES: dict[str, str] = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
}
# Opened by the browser in place; everything else downloads (never HTML or SVG).
INLINE = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
# Configuration sets hold logger programs and modem files with unpredictable names, so they
# take any extension except the ones an operating system will run.
BLOCKED = frozenset({
    ".exe", ".dll", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".js", ".mjs",
    ".jar", ".app", ".apk", ".html", ".htm", ".svg", ".hta", ".lnk", ".reg", ".sh",
})
_EXT = re.compile(r"^\.[a-z0-9]{1,10}$")
_OWNER_PART = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

OWNER_SERVICES: dict[str, str] = {
    "document": "operations",
    "config": "operations",
    "calibration": "operations",
    "visit": "operations",
    "request": "operations",
    "comment": "operations",
    "client_report": "operations",
}


def clean_filename(name: str) -> str:
    """The name to show and to put in `Content-Disposition`: no path, no control characters."""
    base = PurePosixPath(name.replace("\\", "/")).name
    base = "".join(c for c in base if c.isprintable() and c not in '<>:"|?*').strip(" .")
    if not base:
        raise Rejected("bad_filename", "The file needs a name")
    return base[:200]


def extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def check_name(kind: Kind, filename: str) -> str:
    """Return the extension to store under, or raise `Rejected`."""
    ext = extension(filename)
    if kind is Kind.PDF:
        if ext != ".pdf":
            raise Rejected("bad_type", "This must be a PDF file")
        return ext
    if kind is Kind.DOCUMENT:
        if ext not in DOCUMENT_TYPES:
            raise Rejected("bad_type", f"Files of type {ext or '(none)'} can't be uploaded here")
        return ext
    if kind is Kind.CONFIG:
        if ext in BLOCKED:
            raise Rejected("bad_type", f"Files of type {ext} can't be uploaded")
        return ext if _EXT.match(ext) else ""
    allowed = IMAGE_TYPES if kind is Kind.IMAGE else VIDEO_TYPES
    if ext not in allowed:
        what = "a photo" if kind is Kind.IMAGE else "a video"
        raise Rejected("bad_type", f"This must be {what}, not a {ext or '(no extension)'} file")
    return ext


def content_type(filename: str) -> str:
    ext = extension(filename)
    return (DOCUMENT_TYPES.get(ext) or IMAGE_TYPES.get(ext) or VIDEO_TYPES.get(ext)
            or "application/octet-stream")


def disposition(filename: str, *, inline: bool) -> str:
    """`Content-Disposition` for a download. Only PDFs and plain images open in the browser."""
    wanted = inline and extension(filename) in INLINE
    return f"{'inline' if wanted else 'attachment'}; filename*=UTF-8''{quote(filename, safe='')}"


def check_size(kind: Kind, size: int) -> None:
    if size < 1:
        raise Rejected("empty_file", "The file is empty")
    if size > LIMITS[kind]:
        raise Rejected(
            "too_large", f"{kind.value.capitalize()} files can be up to {LIMITS[kind] // MiB} MB"
        )


# --- Who owns it ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Owner:
    ref: str
    service: str
    type: str  # "document-station" for "document:station:<id>"
    id: str


def parse_owner(ref: str) -> Owner:
    """`document:model:<id>`, `document:station:<id>`, `config:<station id>`, and the visit,
    request and comment references later phases add (TRD §5.3)."""
    parts = ref.split(":")
    if len(parts) < 2 or not all(_OWNER_PART.match(p) for p in parts):
        raise Rejected("bad_owner", "The file's owner reference is not valid")
    service = OWNER_SERVICES.get(parts[0])
    if service is None:
        raise Rejected("bad_owner", "The file's owner reference is not valid")
    return Owner(ref=ref, service=service, type="-".join(parts[:-1]), id=parts[-1])


def object_key(org_id: str | None, owner: Owner, media_id: str, ext: str) -> str:
    """Keys are made by the backend and never reused (TRD §10.1)."""
    return f"{org_id or 'shared'}/{owner.type}/{owner.id}/{media_id}/original{ext}"


# --- Parts ---------------------------------------------------------------------------------


def part_count(size: int, part_size: int = PART_SIZE) -> int:
    return math.ceil(size / part_size)


def expected_part_size(number: int, size: int, part_size: int = PART_SIZE) -> int:
    count = part_count(size, part_size)
    return part_size if number < count else size - part_size * (count - 1)


@dataclass(frozen=True)
class PartsCheck:
    missing: list[int]  # parts still to upload: the client carries on
    problem: str | None  # parts that can never add up to the announced file

    @property
    def ok(self) -> bool:
        return not self.missing and self.problem is None


def check_parts(stored: dict[int, int], size: int, part_size: int = PART_SIZE) -> PartsCheck:
    """`stored` maps part number to its size, as the store lists it. The announced size is a
    promise the client made; presigned URLs cannot enforce it, so this is where it is
    checked. Missing parts are for the client to upload; a part that is extra or the wrong
    size means the upload can never be the announced file."""
    count = part_count(size, part_size)
    extra = sorted(n for n in stored if n < 1 or n > count)
    wrong = sorted(
        n for n, s in stored.items()
        if 1 <= n <= count and s != expected_part_size(n, size, part_size)
    )
    problem = None
    if extra:
        problem = f"unexpected parts {extra}"
    elif wrong:
        problem = f"parts {wrong} have the wrong size"
    return PartsCheck([n for n in range(1, count + 1) if n not in stored], problem)


# --- Content -------------------------------------------------------------------------------

_ZIP = (b"PK\x03\x04", b"PK\x05\x06")
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".docx": _ZIP, ".xlsx": _ZIP, ".pptx": _ZIP, ".odt": _ZIP, ".ods": _ZIP,
    ".doc": _OLE, ".xls": _OLE, ".ppt": _OLE,
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
}
_TEXT = frozenset({".txt", ".csv"})
# Boxes a phone's video starts with after its size (MP4, MOV); the brand follows `ftyp`.
_ISO_BOXES = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif")


_JPEG = bytes.fromhex("ffd8ff")
_PNG = bytes.fromhex("89504e470d0a1a0a")
_WEBM = bytes.fromhex("1a45dfa3")


def _looks_like(ext: str, head: bytes) -> bool:
    """The magic bytes of the photo and video types a phone makes."""
    if ext in (".jpg", ".jpeg"):
        return head.startswith(_JPEG)
    if ext == ".png":
        return head.startswith(_PNG)
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext in (".heic", ".heif"):
        return head[4:8] == b"ftyp" and head[8:12] in _HEIF_BRANDS
    if ext in (".mp4", ".m4v", ".mov"):
        return head[4:8] in _ISO_BOXES
    if ext == ".webm":
        return head.startswith(_WEBM)
    return False


def check_content(kind: Kind, filename: str, head: bytes) -> str | None:
    """Compare the first bytes with what the name claims (magic bytes, TRD §15). Returns a
    reason, or None. Configuration files are mostly text but include binary logger programs,
    so they are only held to the blocked-extension rule and the virus scan."""
    ext = extension(filename)
    if kind is Kind.CONFIG:
        return None
    if kind in (Kind.IMAGE, Kind.VIDEO):
        return None if _looks_like(ext, head) else f"the content is not a {ext} file"
    signatures = _MAGIC.get(ext)
    if signatures is not None:
        return None if head.startswith(signatures) else f"the content is not a {ext} file"
    if ext in _TEXT:
        return "the file has binary content" if b"\x00" in head else None
    return None
