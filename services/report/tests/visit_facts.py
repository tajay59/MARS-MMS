"""A made-up visit for the report tests: what operations answers on `report-facts`.

Nothing here is a real station, person or client (the repository is public). Every element is
shared (only shared elements print, W17-1); a test makes one staff-only with `shared=False`. Two stations in two
time zones, a Task with Before and After photos, a Note, a Recommendation, a Config element with a
version, and a video.
"""

from __future__ import annotations

import io
from typing import Any

from mms_common.ids import new_id
from PIL import Image

VISIT = "01900000-0000-7000-8000-00000000b001"
REQUEST = "01900000-0000-7000-8000-00000000c001"
ORG = "01900000-0000-7000-8000-00000000d001"
LEAD = "01900000-0000-7000-8000-00000000e001"
OTHER = "01900000-0000-7000-8000-00000000e002"
S1 = "01900000-0000-7000-8000-0000000000a1"
S2 = "01900000-0000-7000-8000-0000000000a2"
P_BEFORE, P_AFTER, P_NOTE, P_EXTRA, VIDEO, CONFIG_FILE = (
    f"01900000-0000-7000-8000-0000000f000{n}" for n in range(1, 7))
ENDED = "2026-10-05T16:40:00Z"


def webp(size: tuple[int, int] = (1600, 1200), colour: str = "#2a6f97") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, "WEBP")
    return out.getvalue()


def media(media_id: str, kind: str = "image", name: str = "IMG.jpg", caption: str | None = None):
    return {"media_id": media_id, "kind": kind, "filename": name, "caption": caption,
            "captured_at": "2026-10-05T14:05:00Z"}


def element(kind: str, title: str, **over: Any) -> dict[str, Any]:
    return {
        "id": new_id(), "kind": kind, "title": title, "description": None, "items": [],
        "priority": None, "shared": True, "request_ref": None, "config_versions": [],
        "media": {"main": []} if kind in ("note", "recommendation")
        else {"before": [], "after": []},
        "created_by_name": "Test Technician", "created_at": "2026-10-05T14:10:00Z", "version": 1,
        **over,
    }


def facts(visit_id: str = VISIT) -> dict[str, Any]:
    task = element(
        "task", "Replace the rain gauge funnel", description="Cracked funnel",
        items=[{"id": new_id(), "text": "Remove the old funnel", "done": True},
               {"id": new_id(), "text": "Level the gauge", "done": False}],
        media={"before": [media(P_BEFORE, caption="Before")],
               "after": [media(P_AFTER, caption="After")]},
    )
    note = element("note", "Mast and guy wires", description="All tight",
                   media={"main": [media(P_NOTE), media(VIDEO, "video", "clip.mp4", "Walk round")]})
    rec = element("recommendation", "Trim the tree to the east", priority="high",
                  description="Shades the sensors after 3 pm", request_ref="MR-2026-0099",
                  media={"main": [media(P_EXTRA)]})
    config = element(
        "config", "Logger program", description="New sampling interval",
        config_versions=[{"station_id": S2, "version": 4, "note": "Logger program",
                          "files": [{"media_id": CONFIG_FILE, "filename": "program.cr1"}]}],
    )
    return {
        "facts_version": 1,
        "visit": {
            "id": visit_id, "ref": "VR-2026-0042-02", "status": "ended", "version": 6,
            "request_id": REQUEST, "request_ref": "MR-2026-0042",
            "request_title": "Rain gauge not reporting", "org_id": ORG, "org_name": "Test Weather Service",
            "planned_start": "2026-10-05T13:00:00Z", "planned_end": "2026-10-05T18:00:00Z",
            "started_at": "2026-10-05T13:20:00Z", "ended_at": ENDED,
            "additional_visit_required": True, "follow_up_notes": "Bring a new funnel",
            "lead_staff_id": LEAD, "locked": False,
            "staff": [{"id": LEAD, "name": "Test Lead"}, {"id": OTHER, "name": "Test Helper"}],
        },
        "stations": [
            {"station_id": S1, "code": "TST-001", "name": "Test Hill", "type": "AWS",
             "country": "JM", "time_zone": "America/Jamaica", "latitude": 18.0123, "longitude": -76.7891,
             "elevation_m": 120.0, "parameters": ["temperature", "rain"],
             "owner": {"id": LEAD, "name": "Test Lead"},
             "arrived_at": "2026-10-05T13:30:00Z", "departed_at": "2026-10-05T15:00:00Z",
             "next_calibration_due_at": "2026-12-01T00:00:00Z", "elements": [task, note, rec]},
            {"station_id": S2, "code": "TST-002", "name": "Test Bay", "type": "AWS",
             "country": "TT", "time_zone": "America/Port_of_Spain", "latitude": None,
             "longitude": None, "elevation_m": None, "parameters": [],
             "owner": {"id": OTHER, "name": "Test Helper"},
             "arrived_at": "2026-10-05T15:30:00Z", "departed_at": "2026-10-05T16:30:00Z",
             "next_calibration_due_at": None, "elements": [config]},
        ],
    }


ALL_MEDIA = [P_BEFORE, P_AFTER, P_NOTE, P_EXTRA, VIDEO]
