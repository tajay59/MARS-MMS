"""The visit board: Notes, Tasks, Recommendations and Config on a station of a visit (PRD VIS-5,
VIS-7; TRD §3.2.3; decisions W11-16 to W11-35). No I/O.

Each station on a visit has a board of elements, each its own document with its own `version`, so
a conflict covers one element only. Anyone attending (or an admin) adds one; its author, the
station's owner or an admin edits it, ticks its items, changes its files and sharing, and deletes
it, from the visit's start until its report locks it. A deleted element keeps a tombstone, so a
late save from another device cannot bring it back.

The same checks run when a phone's ops sync in Phase 5, so each returns or raises the codes
`/sync` will report (`not_attending`, `not_editor`, `not_started`, `visit_cancelled`, `locked`,
`element_changed`, `element_deleted`, `duplicate_id`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from mms_common.errors import Conflict, Forbidden, NotFound, ValidationFailed

from app.domain.stations.documents import ARRIVED, FileFacts
from app.domain.visits.state import VStatus

KINDS = ("note", "task", "recommendation", "config")
SECTIONS: dict[str, tuple[str, ...]] = {
    "note": ("main",), "task": ("before", "after"),
    "recommendation": ("main",), "config": ("before", "after"),
}
ALL_SECTIONS = ("main", "before", "after")
SHARED_BY_DEFAULT = {"note": False, "task": True, "recommendation": True, "config": False}
PRIORITIES = ("low", "medium", "high")
# Photos and video go anywhere; Config also takes any other file (logger programs, PDFs)
MEDIA_KINDS: dict[str, frozenset[str]] = {
    "note": frozenset({"image", "video"}), "task": frozenset({"image", "video"}),
    "recommendation": frozenset({"image", "video"}),
    "config": frozenset({"image", "video", "config"}),
}

MAX_TITLE = 80
MAX_DESCRIPTION = 4000
MAX_ITEMS = 50
MAX_ITEM = 200
MAX_ELEMENTS = 200  # on one station of one visit
MAX_CAPTION = 300
# A phone's clock can be a little ahead; a photo from next week is a mistake
FUTURE_SLACK = timedelta(days=1)

MEDIA_CHANGES = ("added", "captioned", "hidden", "shown", "removed")


# --- References ---------------------------------------------------------------------------------


def owner_ref(visit_id: str, station_id: str, element_id: str, section: str) -> str:
    """The reference media files an upload under (TRD §5.3, W11-27)."""
    return f"visit:{visit_id}:station:{station_id}:element:{element_id}:{section}"


def parse_owner_ref(ref: str) -> tuple[str, str, str, str] | None:
    """`(visit_id, station_id, element_id, section)`, or None for any other owner."""
    parts = ref.split(":")
    if (len(parts) == 7 and parts[0] == "visit" and parts[2] == "station"
            and parts[4] == "element" and parts[6] in ALL_SECTIONS):
        return parts[1], parts[3], parts[5], parts[6]
    return None


def station_of(visit: Mapping[str, Any], station_id: str) -> Mapping[str, Any]:
    for station in visit["stations"]:
        if station["station_id"] == station_id:
            found: Mapping[str, Any] = station
            return found
    raise NotFound()


# --- Who and when (W11-22, W11-25) --------------------------------------------------------------


def check_open(visit: Mapping[str, Any]) -> None:
    """From the start until the report locks the visit."""
    status = VStatus(visit["status"])
    if status is VStatus.CANCELLED:
        raise Conflict("This visit was cancelled", code="visit_cancelled")
    if status is VStatus.PLANNED:
        raise Conflict("Start the visit first", code="not_started")
    if visit.get("locked"):
        raise Conflict("The visit report has been finalized. Ask an admin to reopen it",
                       code="locked")


def check_can_create(visit: Mapping[str, Any], user_id: str, is_admin: bool) -> None:
    if not (is_admin or user_id in visit["staff_ids"]):
        raise Forbidden("Only the people attending can do this", code="not_attending")
    check_open(visit)


def can_edit(
    element: Mapping[str, Any], station: Mapping[str, Any], user_id: str, is_admin: bool
) -> bool:
    return is_admin or user_id in (element["created_by"], station["owner_staff_id"])


def check_can_edit(
    visit: Mapping[str, Any], station: Mapping[str, Any], element: Mapping[str, Any],
    user_id: str, is_admin: bool,
) -> None:
    if not can_edit(element, station, user_id, is_admin):
        raise Forbidden("Only the person who added it or the station's owner can change it",
                        code="not_editor")
    check_open(visit)


def check_alive(element: Mapping[str, Any]) -> None:
    if element.get("deleted_at") is not None:
        raise Conflict("This was deleted", code="element_deleted")


def check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValidationFailed(f"The kind can be: {', '.join(KINDS)}", code="bad_kind",
                               field="kind")
    return kind


def check_section(kind: str, section: str) -> str:
    if section not in SECTIONS[kind]:
        raise ValidationFailed(f"A {kind} takes files in: {', '.join(SECTIONS[kind])}",
                               code="bad_section", field="section")
    return section


# --- Content ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemIn:
    id: str
    text: str
    done: bool


def _text(value: str | None, field: str, limit: int, *, required: bool = False) -> str | None:
    text = (value or "").strip()
    if required and not text:
        raise ValidationFailed("Give it a title", code="title_required", field=field)
    if len(text) > limit:
        raise ValidationFailed(f"Keep it under {limit} characters", code="too_long", field=field)
    return text or None


def clean_items(
    kind: str, items: Sequence[ItemIn] | None, previous: Sequence[Mapping[str, Any]],
    user_id: str, now: datetime,
) -> list[dict[str, Any]]:
    """A task's checklist. Who ticked an item and when is kept while it stays ticked, set when it
    is ticked and cleared when it is unticked, so a save of unchanged items changes nothing."""
    if kind != "task":
        if items:
            raise ValidationFailed("Only a task has items", code="items_not_allowed",
                                   field="items")
        return []
    given = list(items or [])
    if len(given) > MAX_ITEMS:
        raise ValidationFailed(f"A task can have up to {MAX_ITEMS} items", code="too_many_items",
                               field="items")
    before = {i["id"]: i for i in previous}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in given:
        if item.id in seen:
            raise ValidationFailed("Two items share an id", code="duplicate_id", field="items")
        seen.add(item.id)
        text = _text(item.text, "items", MAX_ITEM)
        if text is None:
            raise ValidationFailed("An item needs some text", code="item_required",
                                   field="items")
        old = before.get(item.id)
        if item.done and old is not None and old.get("done"):
            done_by, done_at = old.get("done_by"), old.get("done_at")
        elif item.done:
            done_by, done_at = user_id, now
        else:
            done_by, done_at = None, None
        out.append({"id": item.id, "text": text, "done": item.done, "done_by": done_by,
                    "done_at": done_at})
    return out


def clean_priority(kind: str, priority: str | None) -> str | None:
    if kind != "recommendation":
        if priority is not None:
            raise ValidationFailed("Only a recommendation has a priority",
                                   code="priority_not_allowed", field="priority")
        return None
    if priority is None:
        return "medium"
    if priority not in PRIORITIES:
        raise ValidationFailed(f"The priority can be: {', '.join(PRIORITIES)}",
                               code="bad_priority", field="priority")
    return priority


def is_complete(items: Sequence[Mapping[str, Any]]) -> bool:
    """A task is complete when it has an item and every item is checked (W11-21)."""
    return bool(items) and all(i["done"] for i in items)


def completed_at(
    kind: str, items: Sequence[Mapping[str, Any]], before: datetime | None, now: datetime
) -> datetime | None:
    if kind != "task" or not is_complete(items):
        return None
    return before or now


def content(
    kind: str, *, title: str | None, description: str | None, items: Sequence[ItemIn] | None,
    priority: str | None, shared: bool | None, previous: Mapping[str, Any] | None,
    user_id: str, now: datetime,
) -> dict[str, Any]:
    """The editable fields, checked and cleaned. `previous` is the element as saved (None for a
    new one): it keeps who ticked an item and when the task became complete."""
    old_items = previous.get("items", []) if previous else []
    cleaned_items = clean_items(kind, items, old_items, user_id, now)
    return {
        "title": _text(title, "title", MAX_TITLE, required=True),
        "description": _text(description, "description", MAX_DESCRIPTION),
        "items": cleaned_items,
        "priority": clean_priority(kind, priority),
        "shared": SHARED_BY_DEFAULT[kind] if shared is None else shared,
        "completed_at": completed_at(
            kind, cleaned_items, previous.get("completed_at") if previous else None, now),
    }


EDITABLE = ("title", "description", "items", "priority", "shared")


def _comparable(fields: Mapping[str, Any]) -> dict[str, Any]:
    items = [{"id": i["id"], "text": i["text"], "done": i["done"]} for i in fields["items"]]
    return {"title": fields["title"], "description": fields["description"], "items": items,
            "priority": fields["priority"], "shared": fields["shared"]}


def same_content(element: Mapping[str, Any], fields: Mapping[str, Any]) -> bool:
    """Whether a save says what is already saved: a retry after a lost answer (W11-26)."""
    return _comparable(element) == _comparable(fields)


def changed_fields(element: Mapping[str, Any], fields: Mapping[str, Any]) -> list[str]:
    a, b = _comparable(element), _comparable(fields)
    return [f for f in EDITABLE if a[f] != b[f]]


def new_element(
    *, element_id: str, visit: Mapping[str, Any], station_id: str, org_id: str, kind: str,
    fields: Mapping[str, Any], user_id: str, user_name: str, device_id: str | None, now: datetime,
) -> dict[str, Any]:
    return {
        "_id": element_id, "visit_id": visit["_id"], "request_id": visit["request_id"],
        "station_id": station_id, "org_id": org_id, "kind": kind, **fields,
        "request_ref": None, "config_version_ids": [], "config_versions": [],
        "media": {s: [] for s in SECTIONS[kind]},
        "created_by": user_id, "created_by_name": user_name, "created_at": now,
        "updated_by": user_id, "updated_at": now, "device_id": device_id,
        # `version` moves with the content (the editor's base); `revision` with every write,
        # media included, and versions the element's events
        "version": 1, "revision": 1, "deleted_at": None,
    }


def check_room(count: int) -> None:
    if count >= MAX_ELEMENTS:
        raise Conflict(f"A station's board can hold up to {MAX_ELEMENTS} notes",
                       code="board_full")


# --- Files (W11-27) -----------------------------------------------------------------------------


def check_caption(caption: str | None) -> str | None:
    if caption is None:
        return None
    text = caption.strip()
    if len(text) > MAX_CAPTION:
        raise ValidationFailed(f"A caption can be up to {MAX_CAPTION} characters",
                               code="caption_too_long", field="caption")
    return text or None


def check_captured_at(captured_at: datetime | None, now: datetime) -> datetime | None:
    if captured_at is not None and captured_at > now + FUTURE_SLACK:
        raise ValidationFailed("That time is in the future", code="captured_in_future",
                               field="captured_at")
    return captured_at


def check_file(facts: FileFacts | None, *, kind: str, owner: str, user_id: str) -> FileFacts:
    """The caller's own upload for this element and section, whole. It may still be going
    through media's checks and processing: the board shows it as such."""
    if facts is None:
        raise ValidationFailed("That file wasn't found", code="unknown_file", field="media_id")
    if facts.owner_ref != owner:
        raise ValidationFailed("That file was uploaded for something else", code="wrong_owner",
                               field="media_id")
    if facts.uploaded_by != user_id:
        raise ValidationFailed("That file was uploaded by someone else", code="not_yours",
                               field="media_id")
    if facts.kind not in MEDIA_KINDS[kind]:
        raise ValidationFailed("That kind of file can't go here", code="wrong_kind",
                               field="media_id")
    if facts.status not in ARRIVED:
        raise ValidationFailed("The upload didn't finish", code="file_not_uploaded",
                               field="media_id")
    return facts


def media_entry(
    facts: FileFacts, *, media_id: str, caption: str | None, captured_at: datetime | None,
    by: str, by_name: str, now: datetime,
) -> dict[str, Any]:
    return {
        "media_id": media_id, "kind": facts.kind, "filename": facts.filename,
        "size_bytes": facts.size_bytes, "caption": caption, "captured_at": captured_at,
        "added_by": by, "added_by_name": by_name, "added_at": now, "hidden": False,
    }


def find_media(element: Mapping[str, Any], media_id: str) -> tuple[str, Mapping[str, Any]]:
    """`(section, entry)` of a file on the element."""
    for section, entries in element.get("media", {}).items():
        for entry in entries:
            if entry["media_id"] == media_id:
                found: Mapping[str, Any] = entry
                return section, found
    raise NotFound()


def has_media(element: Mapping[str, Any], media_id: str) -> bool:
    return any(e["media_id"] == media_id for es in element.get("media", {}).values() for e in es)


def all_media_ids(element: Mapping[str, Any]) -> list[str]:
    return [e["media_id"] for es in element.get("media", {}).values() for e in es]


def shown_media_ids(element: Mapping[str, Any]) -> list[str]:
    """The element's files a client may see when it is shared: all but the ones hidden."""
    return [e["media_id"] for es in element.get("media", {}).values() for e in es
            if not e.get("hidden")]


# --- What the client sees (W11-28) --------------------------------------------------------------


def ended(visit: Mapping[str, Any]) -> bool:
    """Nothing reaches a client before the visit ends, and a cancelled visit shares nothing."""
    return VStatus(visit["status"]) is VStatus.ENDED


def visible_to_client(visit: Mapping[str, Any], element: Mapping[str, Any]) -> bool:
    return ended(visit) and bool(element.get("shared")) and element.get("deleted_at") is None


def sharing_change(
    visit: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any] | None
) -> tuple[list[str], list[str]]:
    """Files to show to the client and files to take back, when an element changes on an ended
    visit: shared or unshared, deleted, or a file hidden, shown, added or removed. Nothing
    changes for the client before the end: the end shares everything at once."""
    if not ended(visit):
        return [], []
    was = set(shown_media_ids(before)) if before.get("shared") else set()
    now = (set(shown_media_ids(after)) if after is not None and after.get("shared")
           and after.get("deleted_at") is None else set())
    return sorted(now - was), sorted(was - now)


def facts(element: Mapping[str, Any]) -> dict[str, Any]:
    """What a board event says about the element: ids and flags, never its text (W11-35)."""
    return {
        "station_id": element["station_id"], "element_id": element["_id"],
        "kind": element["kind"], "shared": bool(element.get("shared")),
        "completed": is_complete(element.get("items", [])) if element["kind"] == "task"
        else None,
        "priority": element.get("priority"), "element_version": element["version"],
    }


@dataclass(frozen=True)
class Summary:
    """A station's board at a glance, for the visit page and the End dialog."""

    counts: dict[str, int]
    incomplete_tasks: int
    cover: tuple[str, str] | None  # (media_id, kind) of the newest photo or video


def summarize(elements: Sequence[Mapping[str, Any]]) -> Summary:
    counts = dict.fromkeys(KINDS, 0)
    incomplete = 0
    cover: tuple[str, str] | None = None
    newest: datetime | None = None
    for element in elements:
        counts[element["kind"]] += 1
        if element["kind"] == "task" and not is_complete(element.get("items", [])):
            incomplete += 1
        for entries in element.get("media", {}).values():
            for entry in entries:
                if entry["kind"] in ("image", "video") and (
                        newest is None or entry["added_at"] > newest):
                    newest, cover = entry["added_at"], (entry["media_id"], entry["kind"])
    return Summary(counts=counts, incomplete_tasks=incomplete, cover=cover)


# --- Config → configuration versions (W11-24, W11-37) -------------------------------------------


def config_files(element: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The files a Config element's version holds: its After files that are not photos or video,
    in the order they were added."""
    if element["kind"] != "config":
        return []
    after = element.get("media", {}).get("after", [])
    return sorted((e for e in after if e["kind"] == "config"), key=lambda e: e["added_at"])


def config_version_due(element: Mapping[str, Any]) -> bool:
    """Whether the After files differ from the last version made from this element. A version
    never changes (CFG-2): a correction makes the next one."""
    files = [e["media_id"] for e in config_files(element)]
    if not files:
        return False
    made = element.get("config_versions", [])
    return not made or sorted(made[-1]["media_ids"]) != sorted(files)


def check_ended_for_version(visit: Mapping[str, Any]) -> None:
    """After the end and before the report locks the visit: the end itself makes the first ones."""
    if VStatus(visit["status"]) is not VStatus.ENDED:
        raise Conflict("The visit's end makes the configuration versions", code="not_ended")
    if visit.get("locked"):
        raise Conflict("The visit report has been finalized. Ask an admin to reopen it",
                       code="locked")


# --- Recommendation → request (W11-23, W11-38) --------------------------------------------------

REQUEST_PRIORITY = {"low": "low", "medium": "normal", "high": "high"}


def check_can_request(element: Mapping[str, Any], request_id: str) -> bool:
    """Whether a request is still to be made: False when this one was made already (a retry).
    One recommendation makes one request."""
    if element["kind"] != "recommendation":
        raise ValidationFailed("Only a recommendation makes a request", code="not_recommendation")
    made = element.get("request_ref")
    if made is None:
        return True
    if made["id"] == request_id:
        return False
    raise Conflict("A request was already made from this", code="already_requested",
                   request_ref=made["ref"])
