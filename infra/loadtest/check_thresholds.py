"""Judge a load test run against the thresholds (PRD NFR-2; plan decision W20-11; W20 slice 6).

    python check_thresholds.py out/soak                                  # Locust's statistics only
    python check_thresholds.py out/soak --prometheus http://127.0.0.1:9090 --window 3600

Reads `<prefix>_stats.csv` written by `locust --csv <prefix>`. A run passes when

- every read (GET) has a 95th percentile under 1 second (NFR-2)
- fewer than 1% of all requests failed
- every summary report was ready within 2 minutes
- (with --prometheus) the oldest unpublished outbox row never passed 30 seconds and no message
  reached a dead-letter topic during the run

The video upload steps are reported, not judged against a number: the plan sets none, and the
first full run on the production host is what writes the numbers down (W11-style lower bounds).
Exit status 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

READ_P95_MS = 1000
FAILURE_RATIO = 0.01
SUMMARY_READY_MS = 120_000
OUTBOX_LAG_S = 30


def rows(prefix: str) -> list[dict[str, str]]:
    path = Path(f"{prefix}_stats.csv")
    if not path.exists():
        sys.exit(f"{path} is missing: run locust with --csv {prefix}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, ValueError):
        return 0.0


def prometheus(url: str, query: str) -> float | None:
    full = f"{url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    with urllib.request.urlopen(full, timeout=20) as response:
        result = json.load(response)["data"]["result"]
    return max((float(item["value"][1]) for item in result), default=None)


def judge(prefix: str, url: str | None, window: int) -> list[tuple[str, bool, str]]:
    table = rows(prefix)
    checks: list[tuple[str, bool, str]] = []

    slow = [
        (r["Name"], number(r, "95%"))
        for r in table
        if r["Type"] == "GET" and number(r, "95%") >= READ_P95_MS
    ]
    reads = [r for r in table if r["Type"] == "GET"]
    worst = max((number(r, "95%") for r in reads), default=0)
    checks.append(
        (
            f"reads: 95th percentile under {READ_P95_MS} ms ({len(reads)} routes)",
            not slow,
            f"slowest {worst:.0f} ms"
            + (f"; over: {', '.join(f'{n} {v:.0f}' for n, v in slow)}" if slow else ""),
        )
    )

    total = next((r for r in table if r["Name"] == "Aggregated"), None)
    if total:
        requests = number(total, "Request Count")
        failed = number(total, "Failure Count")
        ratio = failed / requests if requests else 0.0
        checks.append(
            (
                f"failures under {FAILURE_RATIO:.0%}",
                ratio < FAILURE_RATIO,
                f"{failed:.0f} of {requests:.0f} ({ratio:.2%})",
            )
        )

    summary = next((r for r in table if r["Name"] == "summary ready"), None)
    if summary:
        slowest = number(summary, "Max Response Time")
        checks.append(
            (
                "summary reports ready within 2 minutes",
                number(summary, "Failure Count") == 0 and slowest < SUMMARY_READY_MS,
                f"{number(summary, 'Request Count'):.0f} asked, slowest {slowest / 1000:.1f} s",
            )
        )

    if url:
        lag = prometheus(
            url, f"max_over_time(outbox_oldest_unpublished_seconds[{window}s])"
        )
        checks.append(
            (
                f"outbox never older than {OUTBOX_LAG_S} s",
                lag is not None and lag < OUTBOX_LAG_S,
                "no reading" if lag is None else f"worst {lag:.1f} s",
            )
        )
        dead = prometheus(
            url,
            f'sum(increase(kafka_topic_partition_current_offset{{topic=~"mms\\\\.dlq\\\\..*"}}[{window}s]))',
        )
        checks.append(
            (
                "nothing reached a dead-letter topic",
                dead is not None and dead < 0.5,
                "no reading" if dead is None else f"{dead:.0f} messages",
            )
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "prefix", help="the --csv prefix Locust was given, such as out/soak"
    )
    parser.add_argument(
        "--prometheus", help="Prometheus base URL, to check the outbox and dead letters"
    )
    parser.add_argument(
        "--window", type=int, default=3600, help="seconds the run lasted (default 3600)"
    )
    args = parser.parse_args()

    checks = judge(args.prefix, args.prometheus, args.window)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    for r in rows(args.prefix):
        if r["Type"] in ("UPLOAD", "REPORT") or r["Name"] in (
            "POST /sync (ops)",
            "PUT video part",
        ):
            print(
                f"info  {r['Name']}: {number(r, 'Request Count'):.0f} done, "
                f"median {number(r, '50%') / 1000:.1f} s, 95th {number(r, '95%') / 1000:.1f} s, "
                f"failures {number(r, 'Failure Count'):.0f}"
            )
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
