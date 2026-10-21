"""Checklist templates (PRD VIS-8; TRD §5.4 `checklist_templates`; W10-11, W10-12). No I/O.

A template is a named list of items for one **station type** (a station's free-text `type`,
matched without regard to case) or one **sensor model** (an add-on: its items join the list of
every station that has that model installed). Editing a template never changes it: it writes the
next version, so a visit that copied version 3 keeps meaning version 3.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mms_common.errors import ValidationFailed

MAX_ITEMS = 60
MAX_LABEL = 200
MAX_HELP = 500
MAX_NAME = 100
MAX_TYPE = 60
STATION_GROUP = "Station"


def clean_name(text: str) -> str:
    name = text.strip()
    if not name:
        raise ValidationFailed("Give the template a name", code="required", field="name")
    if len(name) > MAX_NAME:
        raise ValidationFailed(f"Keep it under {MAX_NAME} characters", code="too_long",
                               field="name")
    return name


def clean_scope(
    station_type: str | None, sensor_model_id: str | None
) -> tuple[str | None, str | None]:
    """Exactly one of a station type and a sensor model."""
    stype = station_type.strip() if station_type else None
    if bool(stype) == bool(sensor_model_id):
        raise ValidationFailed("Choose a station type or a sensor model, not both and not neither",
                               code="scope_required", field="station_type")
    if stype and len(stype) > MAX_TYPE:
        raise ValidationFailed(f"Keep it under {MAX_TYPE} characters", code="too_long",
                               field="station_type")
    return stype or None, sensor_model_id or None


def scope_key(station_type: str | None, sensor_model_id: str | None) -> str:
    """What makes two templates compete: one active template per key."""
    if station_type:
        return f"type:{station_type.strip().casefold()}"
    return f"model:{sensor_model_id}"


def clean_items(
    items: Sequence[Mapping[str, Any]], new_id: Callable[[], str]
) -> list[dict[str, str | None]]:
    """One to sixty items. An item keeps its `id` across versions (so results can point at it);
    one without gets a new one."""
    if not items:
        raise ValidationFailed("Add at least one item", code="items_required", field="items")
    if len(items) > MAX_ITEMS:
        raise ValidationFailed(f"A template has at most {MAX_ITEMS} items", code="too_many_items",
                               field="items")
    out: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for item in items:
        label = str(item.get("label", "")).strip()
        if not label:
            raise ValidationFailed("Every item needs a name", code="required", field="items")
        if len(label) > MAX_LABEL:
            raise ValidationFailed(f"Keep an item under {MAX_LABEL} characters", code="too_long",
                                   field="items")
        help_text = (item.get("help") or "").strip() or None
        if help_text and len(help_text) > MAX_HELP:
            raise ValidationFailed(f"Keep the help under {MAX_HELP} characters", code="too_long",
                                   field="items")
        item_id = item.get("id") or new_id()
        if item_id in seen:
            raise ValidationFailed("Two items share an id", code="duplicate_item", field="items")
        seen.add(item_id)
        out.append({"id": item_id, "label": label, "help": help_text})
    return out


@dataclass(frozen=True)
class AddOn:
    """A sensor model installed at the station, and its add-on template if it has one."""

    model_id: str
    label: str  # "Vaisala HMP155"
    template: Mapping[str, Any] | None


def resolve(
    station_template: Mapping[str, Any] | None, add_ons: Sequence[AddOn]
) -> list[dict[str, Any]]:
    """The items a visit to this station is given (W10-11): the station type's template under
    "Station", then, for each installed model that has an add-on, its items under the model's
    name. A model is listed once however many units of it are installed."""
    out: list[dict[str, Any]] = []

    def add(template: Mapping[str, Any], group: str) -> None:
        for item in template["items"]:
            out.append({
                "id": item["id"], "label": item["label"], "help": item.get("help"),
                "group": group, "template_id": template["family_id"],
                "template_version": template["version"],
            })

    if station_template is not None:
        add(station_template, STATION_GROUP)
    seen: set[str] = set()
    for add_on in sorted(add_ons, key=lambda a: a.label.casefold()):
        if add_on.model_id in seen or add_on.template is None:
            continue
        seen.add(add_on.model_id)
        add(add_on.template, add_on.label)
    return out
