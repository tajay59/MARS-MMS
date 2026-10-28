"""Label sheets (PRD QR-6): what goes on a label and how labels fall on A4 pages.

No I/O: the sheet geometry lives in `print.css`, the page and cell counts here, and the two
must agree (a test checks the sheet holds `PER_PAGE` labels).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from mms_common.errors import ValidationFailed

TEMPLATE_VERSION = "labels-1"
COLUMNS, ROWS = 2, 5
PER_PAGE = COLUMNS * ROWS
MAX_STATIONS = 200  # 20 pages; operations' `/internal/labels` takes the same
_PHONE = re.compile(r"^[+(]?[0-9][0-9 ()\-]{3,28}[0-9]$")


class JobType(StrEnum):
    LABELS = "labels"
    SUMMARY = "summary"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Label:
    station_id: str
    code: str
    name: str
    org_name: str
    scan_url: str


def scan_url(app_url: str, token: str) -> str:
    """The address the QR code holds: only the opaque token, never station data (QR-1)."""
    return f"{app_url.rstrip('/')}/s/{token}"


def check_phone(value: str | None) -> str | None:
    """The contact phone printed on every label. Empty means none."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not _PHONE.match(value):
        raise ValidationFailed(
            "Use digits, spaces, brackets and dashes, for example +1 876 555 0100",
            code="invalid_phone", field="contact_phone",
        )
    return value


def paginate(labels: list[Label], per_page: int = PER_PAGE) -> list[list[Label]]:
    """Pages of at most `per_page` labels, in the order given."""
    return [labels[i : i + per_page] for i in range(0, len(labels), per_page)]
