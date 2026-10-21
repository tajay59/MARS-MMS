"""Operator commands, run inside the operations container:

    python -m app.cli import-stations stations.xlsx [--sensors sensors.csv] [--commit]
        The station import (STN-8) from a file copied into the container. A dry run unless
        --commit: it prints every problem with its row number and writes nothing.

    python -m app.cli seed
        Demo stations and sensors for organizations A and B (local and staging only). Run
        auth's seed first. Idempotent: existing codes are skipped.

    python -m app.cli seed-requests [--count 50]
        Example requests ("[Example] ...") for the stations and organizations already here, in
        every status, to look at the requests screens (local and staging only). They go straight
        to the database with no events, so nothing fake enters the audit chain.

    python -m app.cli remove-example-requests
        Deletes the example requests, and only those.

    python -m app.cli backfill-orgs
        Copy every organization from auth's snapshot (TRD §8.6). Also runs at startup.

All of them go through the same rules and the outbox, so the audit trail records them.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
from mms_common import migrations, mongo
from mms_common.auth.service_client import ServiceTokens
from mms_common.events import Actor
from mms_common.ids import new_id
from mms_common.time import SystemClock

from app import migrations as app_migrations
from app.config import Settings
from app.domain.checklists import starter, templates
from app.domain.stations import importing
from app.events.publish import Emitter
from app.jobs import org_backfill, seed_data, seed_requests, station_import
from app.repo.checklists import templates as checklist_repo

CLI = Actor(name="operations cli", roles=["service"])


async def _backfill(settings: Settings, db: Any) -> None:
    """Best effort: the import names organizations, which come from auth."""
    clock = SystemClock()
    async with httpx.AsyncClient() as http:
        tokens = ServiceTokens(settings.auth_url, "operations",
                               settings.service_secret.get_secret_value(), clock, http)
        try:
            count = await org_backfill.backfill_orgs(db, http, tokens, settings.auth_url)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            print(f"Could not refresh organizations from auth: {exc}", file=sys.stderr)
        else:
            print(f"{count} organizations from auth")


async def run_import(tables: dict[str, importing.Table], commit: bool) -> int:
    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    try:
        await migrations.run(db, app_migrations, clock)
        await _backfill(settings, db)
        emitter = Emitter(db, clock, CLI, correlation_id=None)
        report = await station_import.run(client, db, clock, emitter, tables,
                                          dry_run=not commit, by=None)
    finally:
        await client.close()
    verb = "would be created" if report.dry_run else "created"
    print(f"Rows: {report.station_rows} stations, {report.sensor_rows} sensors")
    print(f"Stations {verb}: {report.stations_created}; sensors: {report.sensors_created}; "
          f"new models: {report.models_created}")
    for title, problems in (("Skipped", report.skipped), ("Warnings", report.warnings),
                            ("Errors", report.errors)):
        if problems:
            print(f"\n{title} ({len(problems)}):")
            for p in problems:
                column = f" [{p.column}]" if p.column else ""
                print(f"  {p.sheet} row {p.row}{column}: {p.message}")
    if report.dry_run:
        print("\nDry run: nothing was written. Add --commit to import the valid rows.")
    return 1 if report.errors and not report.stations_created else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    imp = commands.add_parser("import-stations")
    imp.add_argument("file", type=Path, help="XLSX workbook, or the stations CSV")
    imp.add_argument("--sensors", type=Path, help="sensors CSV (with a stations CSV)")
    imp.add_argument("--commit", action="store_true", help="write the valid rows")
    commands.add_parser("seed")
    sr = commands.add_parser("seed-requests")
    sr.add_argument("--count", type=int, default=50)
    commands.add_parser("remove-example-requests")
    commands.add_parser("backfill-orgs")
    sc = commands.add_parser("seed-checklists")
    sc.add_argument("--station-type", default=starter.STARTER_TYPE,
                    help="the station type the starter checklist is for")
    args = parser.parse_args(argv)

    if args.command == "import-stations":
        try:
            tables = importing.read_file(args.file.name, args.file.read_bytes())
            if args.sensors:
                sensors = importing.read_file(args.sensors.name, args.sensors.read_bytes())
                tables[importing.SENSORS] = sensors[importing.STATIONS]
        except (OSError, importing.SheetError) as exc:
            print(exc, file=sys.stderr)
            return 1
        return asyncio.run(run_import(tables, args.commit))
    if args.command == "seed":
        if Settings().environment == "production":
            print("Refusing to seed production", file=sys.stderr)
            return 1
        return asyncio.run(run_import(seed_data.tables(), commit=True))
    if args.command == "seed-requests":
        if Settings().environment == "production":
            print("Refusing to seed production", file=sys.stderr)
            return 1
        return asyncio.run(_seed_requests(args.count))
    if args.command == "remove-example-requests":
        return asyncio.run(_remove_example_requests())
    if args.command == "seed-checklists":
        return asyncio.run(_seed_checklists(args.station_type))
    return asyncio.run(_backfill_only())


async def _seed_checklists(station_type: str) -> int:
    """The starter checklist (PRD Q5) for a station type, once: nothing happens when the type
    already has an active template. Run it on purpose; no migration creates it."""
    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    try:
        await migrations.run(db, app_migrations, clock)
        key = templates.scope_key(station_type, None)
        if await checklist_repo.active_for_scope(db, key) is not None:
            print(f"{station_type} already has an active checklist: nothing changed")
            return 0
        family = new_id()
        items = templates.clean_items(
            [{"label": label, "help": help_} for label, help_ in starter.STARTER_ITEMS], new_id
        )
        await checklist_repo.col(db).insert_one({
            "_id": family, "family_id": family, "name": starter.STARTER_NAME,
            "station_type": station_type, "sensor_model_id": None, "scope_key": key,
            "version": 1, "items": items, "active": True, "is_current": True,
            "created_by": None, "created_at": clock.now(),
        })
    finally:
        await client.close()
    print(f"Created the starter checklist for {station_type}: {len(items)} items")
    return 0


async def _seed_requests(count: int) -> int:
    if not 1 <= count <= 500:
        print("--count is from 1 to 500", file=sys.stderr)
        return 1
    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    db = client[settings.mongo_db]
    try:
        await migrations.run(db, app_migrations, clock)
        if (have := await seed_requests.count_examples(db)) > 0:
            print(f"{have} example requests are already here. Remove them first with "
                  "remove-example-requests.", file=sys.stderr)
            return 1
        made = await seed_requests.run(client, db, clock, count=count)
    finally:
        await client.close()
    if made == 0:
        print("There are no stations to raise requests for. Import or seed stations first.",
              file=sys.stderr)
        return 1
    print(f"{made} example requests made")
    return 0


async def _remove_example_requests() -> int:
    settings = Settings()
    client = mongo.connect(settings.mongo_uri)
    try:
        removed = await seed_requests.remove(client[settings.mongo_db])
    finally:
        await client.close()
    print(f"{removed} example requests removed")
    return 0


async def _backfill_only() -> int:
    settings = Settings()
    client = mongo.connect(settings.mongo_uri)
    try:
        await _backfill(settings, client[settings.mongo_db])
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
