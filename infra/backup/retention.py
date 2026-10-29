"""Which backups to keep (TRD §16.4: 14 daily, 12 monthly; W20-6).

    rclone lsf REMOTE/mongo --include 'mms-*.archive.age' | python3 retention.py

prints the names to delete, one a line. The rule, from the file names alone (UTC):
- the latest backup of each of the newest `daily` days is kept;
- the first backup of each of the newest `monthly` months is kept;
- the newest backup is always kept, whatever else is true.
Names it does not recognise are never printed.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable

NAME = re.compile(r"^mms-(\d{4})(\d{2})(\d{2})T(\d{6})Z\.archive\.age$")


def parse(name: str) -> tuple[str, str, str] | None:
    """(day, month, sortable stamp) of a backup file name, or None."""
    m = NAME.match(name)
    if not m:
        return None
    year, month, day, time = m.groups()
    return f"{year}-{month}-{day}", f"{year}-{month}", f"{year}{month}{day}{time}"


def to_delete(names: Iterable[str], daily: int = 14, monthly: int = 12) -> list[str]:
    found = sorted(
        ((parse(n), n) for n in names if parse(n) is not None),
        key=lambda item: item[0][2],  # type: ignore[index]
    )
    if not found:
        return []
    keep: set[str] = {found[-1][1]}
    last_of_day: dict[str, str] = {}
    first_of_month: dict[str, str] = {}
    for (day, month, _), name in found:  # type: ignore[misc]
        last_of_day[day] = name  # later files overwrite earlier ones
        first_of_month.setdefault(month, name)
    keep.update(last_of_day[d] for d in sorted(last_of_day)[-daily:])
    keep.update(first_of_month[m] for m in sorted(first_of_month)[-monthly:])
    return [name for _, name in found if name not in keep]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", type=int, default=14)
    parser.add_argument("--monthly", type=int, default=12)
    args = parser.parse_args()
    names = (line.strip() for line in sys.stdin if line.strip())
    for name in to_delete(names, args.daily, args.monthly):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
