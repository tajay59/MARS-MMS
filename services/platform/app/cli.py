"""Operator commands, run inside the platform container:

    python -m app.cli verify-audit [--at-seq N --hash H]
        Recomputes the whole audit chain (AUD-5) and exits 0 when it is intact. With --at-seq and
        --hash it also requires the record at that sequence to have that hash: the head a backup
        recorded, so a restore is proved to hold what was backed up (W20-8).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from mms_common import mongo

from app.config import Settings
from app.repo import audit


async def _ignore(_: int) -> None:
    return None


async def check(
    db: Any, at_seq: int | None = None, expected_hash: str | None = None
) -> tuple[int, str]:
    """(exit code, message): 0 intact, 1 broken, 2 the record at `at_seq` is not the expected one"""
    total, _ = await audit.head(db)
    broken = await audit.verify_paged(db, _ignore)
    if broken is not None:
        return 1, f"audit chain BROKEN at seq {broken}"
    if at_seq is not None:
        record = await db["audit_events"].find_one({"seq": at_seq}, {"hash": 1})
        if record is None or record["hash"] != expected_hash:
            return 2, f"audit chain is intact but seq {at_seq} is not the record that was backed up"
    return 0, f"audit chain ok: {total} records"


async def verify_audit(at_seq: int | None, expected_hash: str | None) -> int:
    settings = Settings()
    client = mongo.connect(settings.audit_mongo_uri)
    try:
        code, message = await check(client[settings.audit_db], at_seq, expected_hash)
    finally:
        await client.close()
    print(message, file=sys.stderr if code else sys.stdout)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-audit", help="recompute the audit hash chain")
    verify.add_argument("--at-seq", type=int)
    verify.add_argument("--hash")
    args = parser.parse_args(argv)
    if (args.at_seq is None) != (args.hash is None):
        print("Give --at-seq and --hash together", file=sys.stderr)
        return 1
    return asyncio.run(verify_audit(args.at_seq, args.hash))


if __name__ == "__main__":
    sys.exit(main())
