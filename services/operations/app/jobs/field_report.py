"""What the server holds for a field-test visit (`python -m app.cli field-test-report`; W15-5).

The field test (docs/field-test.md) passes on counts: what the phone says it recorded must be
what the server has, once, after the sync, and the same after a second sync. This reads the
operations database only (it changes nothing) and prints, for each visit, its state, its stations,
its board elements, the files attached to them and the sync operations that arrived. A file
attached twice, an element with no author, or an operation that was claimed but never answered is
listed under "Check".

The files themselves are media's (another service's database, rule 1): this counts the references
on the boards. Media's own view is its status route and the upload list in the app.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from app.domain.visits.elements import all_media_ids
from app.repo.requests import requests as requests_repo
from app.repo.stations.common import Db
from app.repo.sync import operations
from app.repo.visits import elements as elements_repo
from app.repo.visits import visits as visits_repo

DEFAULT_PREFIX = "[Field test]"


def _at(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%SZ") if value else "-"


async def visit_ids_for(db: Db, title_prefix: str) -> list[str]:
    """The visits of the requests whose title starts with the prefix, oldest first."""
    match = {"title": {"$regex": f"^{_escape(title_prefix)}"}}
    cursor = requests_repo.col(db).find(match, {"_id": 1})
    request_ids = [d["_id"] async for d in cursor]
    if not request_ids:
        return []
    found = visits_repo.col(db).find(
        {"request_id": {"$in": request_ids}}, {"_id": 1}).sort("_id", 1)
    return [d["_id"] async for d in found]


def _escape(text: str) -> str:
    return "".join(f"\\{c}" if c in r"\.^$*+?()[]{}|" else c for c in text)


async def gather(db: Db, visit_id: str) -> dict[str, Any] | None:
    visit = await visits_repo.col(db).find_one({"_id": visit_id})
    if visit is None:
        return None
    docs = [d async for d in elements_repo.col(db).find({"visit_id": visit_id})]
    live = [d for d in docs if d.get("deleted_at") is None]
    media_ids = [m for d in live for m in all_media_ids(d)]
    ops = [d async for d in operations(db).find({"visit_id": visit_id})]
    problems: list[str] = []
    for media_id, n in Counter(media_ids).items():
        if n > 1:
            problems.append(f"file {media_id} is attached {n} times")
    for d in live:
        if not d.get("created_by"):
            problems.append(f"element {d['_id']} has no author")
    for op in ops:
        if op.get("result") is None:
            problems.append(f"operation {op['_id']} ({op['type']}) was claimed and has no answer")
    return {
        "id": visit_id,
        "ref": visit.get("ref"),
        "status": visit["status"],
        "started_at": visit.get("started_at"),
        "ended_at": visit.get("ended_at"),
        "stations": [
            {"station_id": s["station_id"], "owner": s.get("owner_staff_id"),
             "arrived_at": s.get("arrived_at"), "departed_at": s.get("departed_at"),
             "elements": Counter(d["kind"] for d in live if d["station_id"] == s["station_id"])}
            for s in visit["stations"]
        ],
        "elements": len(live),
        "deleted": len(docs) - len(live),
        "files": len(media_ids),
        "operations": Counter(op["type"] for op in ops),
        "devices": sorted({op["device_id"] for op in ops if op.get("device_id")}),
        "problems": problems,
    }


def format_visit(report: dict[str, Any]) -> str:
    lines = [
        f"{report['ref']}  {report['status']}  ({report['id']})",
        f"  started {_at(report['started_at'])}  ended {_at(report['ended_at'])}",
    ]
    for s in report["stations"]:
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(s["elements"].items())) or "no elements"
        lines.append(f"  station {s['station_id']}: arrived {_at(s['arrived_at'])}  "
                     f"departed {_at(s['departed_at'])}  {kinds}")
    lines.append(f"  elements {report['elements']} (deleted {report['deleted']}), "
                 f"files on boards {report['files']}")
    ops = ", ".join(f"{n} {t}" for t, n in sorted(report["operations"].items())) or "none"
    lines.append(f"  sync operations {sum(report['operations'].values())}: {ops}")
    devices = ", ".join(d[:4] + "…" + d[-4:] for d in report["devices"]) or "none"
    lines.append(f"  devices: {devices}")
    lines.append("  Check: " + ("; ".join(report["problems"]) if report["problems"] else "nothing"))
    return "\n".join(lines)


async def run(db: Db, visit_ids: list[str]) -> tuple[str, int]:
    """The text for these visits and how many problems it found (any makes the CLI exit 1)."""
    parts: list[str] = []
    problems = 0
    for visit_id in visit_ids:
        report = await gather(db, visit_id)
        if report is None:
            parts.append(f"{visit_id}  not found")
            problems += 1
            continue
        problems += len(report["problems"])
        parts.append(format_visit(report))
    return "\n\n".join(parts), problems
