"""Organizations from the organization's existing system (decision W5-8; TRD T4). No I/O here.

The source is a MongoDB export of its `entities` collection: a JSON array (`mongoexport
--jsonArray`) or one document per line. Each document becomes an organization:

| Source         | Organization  |
| -------------- | ------------- |
| `organization` | `name` (the full name; `name` when there is none) |
| `name`         | `short_name` (an acronym such as ABC) |
| `code`         | `country` (ISO 3166-1 alpha-2) |
| `id`           | `external_id`, which the station import matches `site.entity` against |

Nothing else is read. The documents also hold MQTT usernames and passwords (`web`, `device`):
they are never copied, logged or reported. An organization whose external ID or name already
exists is skipped, so the import can run again.
"""

from __future__ import annotations

import json
import re
from collections.abc import Container
from dataclasses import dataclass, field
from typing import Any

from app.domain.users import org_name_key

_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
MAX_ORGS = 1000


class ExportError(ValueError):
    """The file as a whole can't be read."""


@dataclass(frozen=True)
class OrgRow:
    number: int  # the document's position in the file, from 1
    name: str
    short_name: str | None
    country: str
    external_id: str


@dataclass(frozen=True)
class Problem:
    number: int
    message: str


@dataclass
class OrgPlan:
    create: list[OrgRow] = field(default_factory=list)
    skipped: list[Problem] = field(default_factory=list)
    errors: list[Problem] = field(default_factory=list)


def read_export(content: bytes) -> list[dict[str, Any]]:
    """The documents in a mongoexport file (a JSON array or JSON lines)."""
    try:
        text = content.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ExportError("The file is not UTF-8 text") from exc
    if not text:
        return []
    try:
        if text.startswith("["):
            docs = json.loads(text)
        else:
            docs = [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ExportError(f"The file is not JSON (line {exc.lineno})") from exc
    if not isinstance(docs, list) or not all(isinstance(d, dict) for d in docs):
        raise ExportError("Expected one JSON object per organization")
    if len(docs) > MAX_ORGS:
        raise ExportError(f"Import at most {MAX_ORGS} organizations at once")
    return docs


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def plan(
    docs: list[dict[str, Any]],
    *,
    existing_external_ids: Container[str],
    existing_name_keys: Container[str],
) -> OrgPlan:
    result = OrgPlan()
    seen_ids: dict[str, int] = {}
    seen_names: dict[str, int] = {}
    for number, doc in enumerate(docs, start=1):
        external_id = _text(doc.get("id"))
        short = _text(doc.get("name"))
        full = _text(doc.get("organization"))
        name = full or short
        country = (_text(doc.get("code")) or "").upper()
        problems = []
        if external_id is None or not _EXTERNAL_ID.match(external_id):
            problems.append("no usable id")
        if name is None or len(name) > 200:
            problems.append("no organization or name (at most 200 characters)")
        if not _COUNTRY.match(country):
            problems.append(f"code {country or '(empty)'} is not a two-letter country code")
        if short is not None and len(short) > 40:
            problems.append("name is longer than 40 characters")
        label = name or external_id or f"document {number}"
        if problems:
            result.errors.append(Problem(number, f"{label}: {'; '.join(problems)}"))
            continue
        assert external_id is not None and name is not None  # noqa: S101 - checked above
        key = org_name_key(name)
        if external_id in seen_ids or key in seen_names:
            first = seen_ids.get(external_id) or seen_names[key]
            result.errors.append(Problem(number, f"{label}: also in document {first}"))
            continue
        seen_ids[external_id], seen_names[key] = number, number
        if external_id in existing_external_ids or key in existing_name_keys:
            result.skipped.append(Problem(number, f"{label}: already exists"))
            continue
        result.create.append(OrgRow(
            number=number, name=name, short_name=short if short != name else None,
            country=country, external_id=external_id,
        ))
    return result
