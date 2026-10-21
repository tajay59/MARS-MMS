# ruff: noqa: E501
"""Example requests for testing the requests screens (`python -m app.cli seed-requests`).

They are made-up work orders for the stations and organizations already in the database, with
statuses spread across the whole workflow so every state of the list and the request page can be
looked at. Each one is marked `example: true` and titled "[Example] ..." so it can be told apart
and removed (`remove-example-requests`).

They are written straight to the `requests` collection, with no events: a seed must not put
fake entries into the audit chain, which nothing can ever delete (rule 10). Nobody real is named:
the people in their history are "Example requester", "Example admin" and "Example technician".
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from mms_common.ids import IdGenerator
from mms_common.mongo import in_transaction
from mms_common.time import Clock, ManualClock
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.requests.state import MILESTONES, Status
from app.repo.requests import requests as repo
from app.repo.stations.common import stamp

EXAMPLE_REQUESTER = ("example-requester", "Example requester")
EXAMPLE_ADMIN = ("example-admin", "Example admin")
EXAMPLE_TECHNICIAN = ("example-technician", "Example technician")

# Out of 50: what the list should show. Scaled to the count asked for.
MIX: list[tuple[str, int]] = [
    ("submitted", 14), ("approved", 9), ("assigned", 6), ("scheduled", 3), ("in_progress", 4),
    ("client_review", 3), ("closed", 5), ("denied", 3), ("cancelled", 3),
]

PROBLEMS: dict[str, list[tuple[str, str]]] = {
    "fault": [
        ("Rain gauge not reporting", "The rain gauge stopped sending readings on Saturday. The logger still reports temperature and humidity."),
        ("Wind sensor cups do not turn", "The anemometer reads zero in a steady breeze. It may be seized."),
        ("Humidity reading stuck at 100%", "Relative humidity has been flat at 100% for three days, including in the afternoon sun."),
        ("Logger restarts every night", "The data logger restarts at about 02:00 every night and loses an hour of readings."),
    ],
    "communications": [
        ("Modem offline since Friday", "No data has arrived since Friday afternoon. The SIM was last topped up in August."),
        ("Intermittent signal at night", "Readings arrive in bursts after midnight. Daytime reporting is normal."),
    ],
    "power": [
        ("Battery voltage dropping at night", "Night-time battery voltage falls below 11.5 V. The panel may be shaded by a new tree."),
        ("Solar panel cracked", "A crack is visible across the lower left corner of the panel."),
    ],
    "calibration": [
        ("Sensor overdue for calibration", "The temperature sensor passed its calibration date last month."),
        ("Calibration check after a failed reading", "A reference thermometer disagrees with the station by 1.5 degrees."),
    ],
    "relocation": [
        ("Move the station away from the new building", "A new building now shades the site in the morning. We would like the station moved."),
    ],
    "inspection": [
        ("Annual inspection", "Routine yearly inspection of the site, enclosure and mast."),
        ("Check the fence and gate lock", "The gate lock is rusted and the fence has a gap on the north side."),
    ],
    "other": [
        ("Question about the station's data format", "We would like a short note on the units used in the daily file."),
    ],
}
CATEGORY_WEIGHTS = {"fault": 8, "communications": 4, "power": 3, "calibration": 3, "relocation": 1,
                    "inspection": 3, "other": 1}
PRIORITY_WEIGHTS = {"low": 2, "normal": 8, "high": 3, "urgent": 1}

# The statuses a request passes through on its way to each status (PRD §5.1)
PATH: dict[str, list[str]] = {
    "submitted": ["submitted"],
    "approved": ["submitted", "approved"],
    "assigned": ["submitted", "approved", "assigned"],
    "scheduled": ["submitted", "approved", "assigned", "scheduled"],
    "in_progress": ["submitted", "approved", "assigned", "scheduled", "in_progress"],
    "client_review": ["submitted", "approved", "assigned", "scheduled", "in_progress", "client_review"],
    "closed": ["submitted", "approved", "assigned", "scheduled", "in_progress", "client_review", "closed"],
    "denied": ["submitted", "denied"],
    "cancelled": ["submitted", "approved", "cancelled"],
}
DENIAL_REASONS = (
    "This station is outside the maintenance contract. Please contact your account manager.",
    "The fault is covered by the manufacturer's warranty: please raise it with them.",
    "Duplicate of an open request for the same station.",
)
CANCEL_REASONS = (
    "The fault fixed itself.", "Raised by mistake.", "The station was taken out of service.",
)
MARKER = "example"


def _scaled(count: int) -> list[str]:
    """`count` statuses in the proportions of `MIX`, every status present when there is room."""
    total = sum(n for _, n in MIX)
    out: list[str] = []
    for status, n in MIX:
        out.extend([status] * max(1, round(n * count / total)) if count >= len(MIX) else [])
    while len(out) > count:
        out.remove(max(set(out), key=out.count))
    while len(out) < count:
        out.append(MIX[len(out) % len(MIX)][0])
    return out


async def _stations_by_org(db: AsyncDatabase[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    async for s in db["stations"].find({}, {"_id": 1, "owner_org_id": 1}).sort("code", 1):
        out.setdefault(s["owner_org_id"], []).append(s)
    return out


def build(
    index: int, status: str, org_id: str, station_ids: list[str], created: datetime, now: datetime,
    rng: random.Random,
) -> dict[str, Any]:
    """One example request in `status`, created at `created`, with a history that follows the
    workflow and never runs past `now`."""
    category = rng.choices(list(CATEGORY_WEIGHTS), weights=list(CATEGORY_WEIGHTS.values()))[0]
    title, description = rng.choice(PROBLEMS[category])
    path = PATH[status]
    by_admin = status not in ("submitted", "denied") and rng.random() < 0.15
    if by_admin:
        path = path[1:]  # raised by an admin: it starts Approved (REQ-2)
    # Each step comes a few hours to a few days after the one before, never later than now
    at = created
    history: list[dict[str, Any]] = []
    previous: str | None = None
    for step in path:
        if previous is not None:
            at = min(now, at + timedelta(hours=rng.randint(2, 70)))
        person = EXAMPLE_ADMIN if step in ("approved", "denied", "cancelled") or by_admin and previous is None \
            else (EXAMPLE_REQUESTER if step == "submitted" else EXAMPLE_TECHNICIAN)
        if step == "client_review":
            person = EXAMPLE_TECHNICIAN
        if step == "closed":
            person = EXAMPLE_REQUESTER
        note = None
        if step == "denied":
            note = rng.choice(DENIAL_REASONS)
        elif step == "cancelled":
            note = rng.choice(CANCEL_REASONS)
        history.append({
            "from": previous, "to": step, "by": person[0], "by_name": person[1], "at": at,
            "note": note, "event_id": None,
        })
        previous = step
    milestones: dict[str, datetime] = {"submitted_at": created}
    for entry in history:
        key = MILESTONES.get(Status(entry["to"]))
        if key and key not in milestones:
            milestones[key] = entry["at"]
    staff = [list(EXAMPLE_TECHNICIAN)] if status in (
        "assigned", "scheduled", "in_progress", "client_review", "closed") else []
    doc = stamp({
        "org_id": org_id, "station_ids": station_ids, "title": f"[Example] {title}",
        "description": description, "category": category,
        "priority": rng.choices(list(PRIORITY_WEIGHTS), weights=list(PRIORITY_WEIGHTS.values()))[0],
        "status": status, "status_history": history,
        "assigned_staff_ids": [s[0] for s in staff], "assigned_staff": staff,
        "denial_reason": next((h["note"] for h in history if h["to"] == "denied"), None),
        "cancel_reason": next((h["note"] for h in history if h["to"] == "cancelled"), None),
        "rework_since": None, "review_started_at": milestones.get("review_started_at"),
        "reminders_sent": [], "client_verification": None, "reopen_count": 0, "attachments": [],
        "milestones": milestones, "requester_name": EXAMPLE_REQUESTER[1], MARKER: True,
    }, created, EXAMPLE_REQUESTER[0])
    doc["updated_at"] = history[-1]["at"]
    doc["version"] = len(history)
    return doc


async def count_examples(db: AsyncDatabase[dict[str, Any]]) -> int:
    return int(await repo.col(db).count_documents({MARKER: True}))


async def run(
    client: AsyncMongoClient[dict[str, Any]], db: AsyncDatabase[dict[str, Any]], clock: Clock,
    *, count: int = 50, seed: int = 20261021, spread_days: int = 60,
) -> int:
    """Writes `count` example requests (oldest first, so the IDs sort by date) and returns how
    many were made. Nothing is written when there are no stations to raise them for."""
    by_org = await _stations_by_org(db)
    if not by_org:
        return 0
    rng = random.Random(seed)  # noqa: S311  (made-up data, not a secret)
    orgs = sorted(by_org)
    now = clock.now()
    statuses = _scaled(count)
    rng.shuffle(statuses)
    # Dates run from `spread_days` ago up to today, in order
    created_at = sorted(now - timedelta(minutes=rng.randint(30, spread_days * 24 * 60)) for _ in statuses)
    made = 0
    for index, (status, created) in enumerate(zip(statuses, created_at, strict=True)):
        org_id = rng.choice(orgs)
        pool = [s["_id"] for s in by_org[org_id]]
        station_ids = rng.sample(pool, k=min(len(pool), rng.choices([1, 2, 3], weights=[7, 2, 1])[0]))
        doc = build(index, status, org_id, station_ids, created, now, rng)
        doc["_id"] = IdGenerator(ManualClock(created)).new()  # an ID that sorts by its date

        async def save(s: AsyncClientSession, doc: dict[str, Any] = doc, created: datetime = created) -> None:
            doc["ref"] = await repo.next_ref(db, created, s)
            await repo.insert(db, doc, s)

        await in_transaction(client, save)
        made += 1
    return made


async def remove(db: AsyncDatabase[dict[str, Any]]) -> int:
    """Deletes the example requests (and only those). The reference counter is left as it is."""
    result = await repo.col(db).delete_many({MARKER: True})
    return int(result.deleted_count)
