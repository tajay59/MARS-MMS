"""Comments and attachments on a request (PRD REQ-3, REQ-9, REQ-10; W9-6 to W9-9). No I/O.

A comment is a flat thread entry. The author edits the text within 15 minutes; staff may mark
their own comment internal (never shown to clients, files included). A comment holds up to five
PDFs, each already uploaded and checked, so nothing unchecked is ever attached.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain.requests.state import Who
from app.domain.stations.documents import FileFacts, check_file

MAX_BODY = 5000
MAX_ATTACHMENTS = 5
MAX_FILE_BYTES = 25 * 1024 * 1024
EDIT_WINDOW = timedelta(minutes=15)
ATTACHMENT_KINDS = frozenset({"pdf"})


def request_owner_ref(request_id: str) -> str:
    """The reference media files a request's own attachments under (TRD §5.3)."""
    return f"request:{request_id}"


def comment_owner_ref(request_id: str, comment_id: str) -> str:
    return f"comment:{request_id}:{comment_id}"


def clean_body(text: str) -> str:
    body = text.strip()
    if not body:
        raise ValidationFailed("Write something", code="required", field="body")
    if len(body) > MAX_BODY:
        raise ValidationFailed(f"Keep it under {MAX_BODY:,} characters", code="too_long",
                               field="body")
    return body


def is_internal(wanted: bool, who: Who) -> bool:
    """Only staff mark a comment internal. A client's flag is ignored, never an error: the
    page doesn't offer it, so an old or forged request just gets a normal comment."""
    return wanted and who in (Who.TECHNICIAN, Who.ADMIN)


def role_of(who: Who) -> str:
    return who.value


def within_edit_window(created_at: datetime, now: datetime) -> bool:
    return now - created_at <= EDIT_WINDOW


def check_can_edit(
    comment_author_id: str, created_at: datetime, user_id: str, now: datetime
) -> None:
    if comment_author_id != user_id:
        raise Forbidden()
    if not within_edit_window(created_at, now):
        raise Conflict("A comment can be changed for 15 minutes after it is posted",
                       code="edit_window_closed")


def check_media_ids(media_ids: Sequence[str]) -> list[str]:
    unique = list(dict.fromkeys(media_ids))
    if len(unique) > MAX_ATTACHMENTS:
        raise ValidationFailed(f"Attach up to {MAX_ATTACHMENTS} files", code="too_many_files",
                               field="media_ids")
    return unique


def check_attachment(facts: FileFacts | None, *, owner: str, user_id: str) -> FileFacts:
    """A PDF the author uploaded for this owner, checked and clean, within the size limit."""
    checked = check_file(facts, owner=owner, kinds=ATTACHMENT_KINDS, user_id=user_id,
                         ready_only=True)
    if checked.size_bytes > MAX_FILE_BYTES:
        raise ValidationFailed(
            f"{checked.filename} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB",
            code="too_large", field="media_ids",
        )
    return checked
