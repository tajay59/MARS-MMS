"""The load test's verdict (W20 slice 6): the threshold check passes a good run and fails each kind of
bad one. Pure Python on made-up statistics, so it runs anywhere and keeps the check honest."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "loadtest"))
import check_thresholds

COLUMNS = ["Type", "Name", "Request Count", "Failure Count", "Median Response Time",
           "Max Response Time", "50%", "95%"]


def write(tmp_path: Path, rows: list[dict[str, object]]) -> str:
    prefix = str(tmp_path / "run")
    with Path(f"{prefix}_stats.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, restval=0)
        writer.writeheader()
        writer.writerows(rows)
    return prefix


def row(kind: str, name: str, count: int = 100, failed: int = 0, p95: int = 40, worst: int = 100):
    return {"Type": kind, "Name": name, "Request Count": count, "Failure Count": failed,
            "Median Response Time": 20, "Max Response Time": worst, "50%": 20, "95%": p95}


def verdict(tmp_path, rows):
    checks = check_thresholds.judge(write(tmp_path, rows), None, 3600)
    return {name.split(":")[0].split(" (")[0]: ok for name, ok, _ in checks}


GOOD = [row("GET", "GET /stations"), row("GET", "GET /dashboard", p95=300), row("", "Aggregated", 200)]


def test_a_good_run_passes(tmp_path):
    assert all(verdict(tmp_path, GOOD).values())


def test_a_slow_read_fails_even_when_the_average_is_fine(tmp_path):
    slow = [*GOOD[:1], row("GET", "GET /requests", p95=1500), GOOD[2]]
    assert not verdict(tmp_path, slow)["reads"]


def test_a_read_at_exactly_one_second_fails(tmp_path):
    assert not verdict(tmp_path, [row("GET", "GET /x", p95=1000), GOOD[2]])["reads"]


def test_a_slow_write_does_not_fail_the_read_check(tmp_path):
    rows = [*GOOD[:2], row("POST", "POST /sync (ops)", p95=5000), GOOD[2]]
    assert verdict(tmp_path, rows)["reads"]


@pytest.mark.parametrize(("failed", "passes"), [(0, True), (1, True), (2, False), (10, False)])
def test_one_percent_of_requests_failing_fails_the_run(tmp_path, failed, passes):
    """Of 200 requests, 1 failure is half a percent; 2 is exactly one percent, which is too many."""
    rows = [*GOOD[:2], row("", "Aggregated", 200, failed=failed)]
    assert verdict(tmp_path, rows)["failures under 1%"] is passes


def test_a_summary_report_taking_over_two_minutes_fails(tmp_path):
    slow = [*GOOD, row("REPORT", "summary ready", 3, worst=130_000)]
    assert not verdict(tmp_path, slow)["summary reports ready within 2 minutes"]
    quick = [*GOOD, row("REPORT", "summary ready", 3, worst=9_000)]
    assert verdict(tmp_path, quick)["summary reports ready within 2 minutes"]


def test_a_failed_summary_report_fails(tmp_path):
    rows = [*GOOD, row("REPORT", "summary ready", 3, failed=1, worst=500)]
    assert not verdict(tmp_path, rows)["summary reports ready within 2 minutes"]
