"""Operator commands, run inside the report container:

    python -m app.cli backfill
        Build the read model from operations' snapshots (TRD §8.6): stations, requests, visits
        and calibrations. Safe to repeat: an item is written only if it is newer than the stored
        one, so events that arrive meanwhile are never overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from mms_common import migrations, mongo
from mms_common.time import SystemClock

from app import migrations as app_migrations
from app.config import Settings
from app.jobs import backfill
from app.repo.operations import OperationsUnavailable
from app.services import make_stations


async def _backfill() -> int:
    settings = Settings()
    clock = SystemClock()
    client = mongo.connect(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        await migrations.run(db, app_migrations, clock)
        async with httpx.AsyncClient() as http:
            source = make_stations(settings, clock, http)
            try:
                counts = await backfill.backfill(db, source)
            except OperationsUnavailable as exc:
                print(f"Operations did not answer: {exc}", file=sys.stderr)
                return 1
    finally:
        await client.close()
    for entity, (read, written) in counts.items():
        print(f"{entity}: {read} read, {written} written")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backfill")
    parser.parse_args(argv)
    return asyncio.run(_backfill())


if __name__ == "__main__":
    sys.exit(main())
