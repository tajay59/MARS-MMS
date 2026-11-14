"""What a visit report prints, how it is edited, and the hash a signature is bound to (TRD 11.2,
11.3; PRD RPT-2, RPT-4; W17-1 to W17-3). No I/O.

A report's `content` holds the board's `facts` (everything operations answered, staff-only
elements too, so the editor can mark them), the `narrative` people write and the `media_selection`.
Only **shared** elements print (W17-1): a final report is one PDF a client may download, so a
staff-only note never reaches it. `printed` is that projection and `content_hash` its SHA-256: a
signature stands for exactly that, and a change that alters the hash clears the signatures. Fields
that move without changing the page (the visit's version, a lock, an element's version) are not in
it, so locking the visit does not invalidate anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from mms_common.errors import ValidationFailed

from app.domain import drafts

SUMMARY_MAX = 4_000
STATION_TEXT_MAX = 8_000
RECOMMENDATIONS_MAX = 4_000
FOLLOW_UP_MAX = 4_000
CAPTION_MAX = 200

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def plain(text: str) -> str:
    """Text as typed: line endings made `\\n`, control characters (not tab or newline) dropped.
    It is printed escaped, so nothing else needs removing."""
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


# --- what prints ---------------------------------------------------------------------------------


def shared_elements(station: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [e for e in station["elements"] if e.get("shared")]


def _element(e: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": e["id"], "kind": e["kind"], "title": e["title"],
        "description": e.get("description"), "items": e["items"], "priority": e.get("priority"),
        "request_ref": e.get("request_ref"), "config_versions": e["config_versions"],
        "media": e["media"],
    }


def printed_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The facts as the page uses them: shared elements only, and none of the counters."""
    visit = facts["visit"]
    return {
        "visit": {k: visit.get(k) for k in (
            "id", "ref", "request_ref", "request_title", "org_name", "started_at", "ended_at",
            "additional_visit_required", "follow_up_notes", "lead_staff_id")}
        | {"staff": [{"id": p["id"], "name": p["name"]} for p in visit["staff"]]},
        "stations": [
            {k: s.get(k) for k in (
                "station_id", "code", "name", "type", "country", "time_zone", "latitude",
                "longitude", "elevation_m", "parameters", "arrived_at", "departed_at",
                "next_calibration_due_at")}
            | {"owner": (s.get("owner") or {}).get("name"),
               "elements": [_element(e) for e in shared_elements(s)]}
            for s in facts["stations"]
        ],
    }


def printed(content: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "facts": printed_facts(content["facts"]),
        "narrative": content["narrative"],
        "media_selection": sorted(content["media_selection"], key=lambda s: s["media_id"]),
    }


def content_hash(content: Mapping[str, Any]) -> str:
    """SHA-256 of the printed content as canonical JSON (sorted keys, UTF-8, no spaces)."""
    canonical = json.dumps(
        printed(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def client_view(content: Mapping[str, Any]) -> dict[str, Any]:
    """A client reads a final report's content with the staff-only elements taken out (rule 6)."""
    facts = content["facts"]
    keep = {r["media_id"] for r in drafts.media_refs(facts, shared_only=True)}
    return {
        "facts": {
            "facts_version": facts.get("facts_version"),
            "visit": facts["visit"],
            "stations": [{**s, "elements": shared_elements(s)} for s in facts["stations"]],
        },
        "narrative": content["narrative"],
        "media_selection": [s for s in content["media_selection"] if s["media_id"] in keep],
    }


# --- editing -------------------------------------------------------------------------------------


def _text(value: str, limit: int, field: str) -> str:
    cleaned = plain(value)
    if len(cleaned) > limit:
        raise ValidationFailed(f"{field} is too long (at most {limit} characters)", code="too_long",
                               field=field)
    return cleaned


def edited(
    content: Mapping[str, Any],
    *,
    narrative: Mapping[str, Any] | None,
    media_selection: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """`content` with an edit applied: a narrative field that is given replaces the old one; a
    selection entry that is given (by `media_id`) changes that photo's `in_body` and caption and
    the others stay. Raises `ValidationFailed` for a station or photo the report does not have,
    or more than six photos in one station's body."""
    new = {
        "facts": content["facts"],
        "narrative": dict(content["narrative"]),
        "media_selection": [dict(s) for s in content["media_selection"]],
    }
    if narrative:
        for field, limit in (("summary", SUMMARY_MAX), ("recommendations", RECOMMENDATIONS_MAX),
                             ("follow_up", FOLLOW_UP_MAX)):
            if narrative.get(field) is not None:
                new["narrative"][field] = _text(narrative[field], limit, field)
        if narrative.get("stations") is not None:
            by_station = {s["station_id"]: dict(s) for s in new["narrative"]["stations"]}
            for entry in narrative["stations"]:
                if entry["station_id"] not in by_station:
                    raise ValidationFailed(
                        "That station is not on this visit", code="unknown_station",
                        field="stations")
                by_station[entry["station_id"]]["work_performed"] = _text(
                    entry["work_performed"], STATION_TEXT_MAX, "work_performed")
            new["narrative"]["stations"] = list(by_station.values())
    if media_selection:
        chosen = {s["media_id"]: s for s in new["media_selection"]}
        for entry in media_selection:
            current = chosen.get(entry["media_id"])
            if current is None:
                raise ValidationFailed("That photo is not available for this report",
                                       code="unknown_photo", field="media_selection")
            if entry.get("in_body") is not None:
                current["in_body"] = bool(entry["in_body"])
            if "caption" in entry:
                caption = entry["caption"]
                current["caption"] = _text(caption, CAPTION_MAX, "caption") if caption else None
        crowded = {
            station for station in {s["station_id"] for s in new["media_selection"]}
            if sum(1 for s in new["media_selection"]
                   if s["station_id"] == station and s["in_body"]) > drafts.PER_STATION_IN_BODY
        }
        if crowded:
            raise ValidationFailed(
                f"At most {drafts.PER_STATION_IN_BODY} photos go in the body for each station",
                code="too_many_in_body", field="media_selection")
    return new
