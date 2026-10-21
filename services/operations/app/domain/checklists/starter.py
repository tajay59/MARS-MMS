"""The starter checklist (PRD Q5): a typical automatic weather station site visit, to be corrected
by the people who do the visits. Created by `python -m app.cli seed-checklists`, never by a
migration, so nothing appears in production until someone asks for it."""

from __future__ import annotations

STARTER_NAME = "Automatic weather station visit"
STARTER_TYPE = "AWS"

STARTER_ITEMS: tuple[tuple[str, str | None], ...] = (
    ("Site access and security: fence, gate, lock, signs", None),
    ("Mast or tower: condition, guy wires, corrosion, grounding", None),
    ("Vegetation and obstructions around the sensors",
     "Anything that shades, shelters or touches a sensor"),
    ("Enclosure: seals, desiccant, water inside, pests", None),
    ("Power: solar panel clean and angled, battery voltage, charge controller status",
     "Note the battery voltage"),
    ("Datalogger: clock against a reference, program name, memory", None),
    ("Communications: signal strength, SIM or antenna, last successful upload", None),
    ("Each sensor: mounted level, clean, cable and connector, reading plausible against a "
     "reference", None),
    ("Rain gauge: funnel clear, level, tipping bucket moves freely", None),
    ("Data downloaded (and the period) or confirmed as sent", None),
    ("Photos: before, after, and any damage", None),
    ("Anything left to do on the next visit", None),
)
