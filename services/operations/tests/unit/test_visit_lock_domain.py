"""The visit lock and the visit's report fields, W17 (PRD VIS-12, RPT-6; TRD 11.2). Pure rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mms_common.errors import Conflict

from app.domain.visits import lock

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
R1, R2 = "report-1", "report-2"


def visit(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"status": "ended", "locked": False}
    base.update(over)
    return base


def locked_for(report_id: str = R1, version: int = 1) -> dict[str, Any]:
    return visit(locked=True, locked_for={"report_id": report_id, "version": version})


@pytest.mark.req("VIS-12")
def test_an_ended_visit_is_locked_for_one_report_version():
    change = lock.lock(visit(), R1, 1, NOW)
    assert change.locked
    assert change.fields == {
        "locked": True, "locked_for": {"report_id": R1, "version": 1}, "locked_at": NOW,
    }


@pytest.mark.req("VIS-12")
@pytest.mark.parametrize("status", ["planned", "started", "cancelled"])
def test_only_an_ended_visit_can_be_locked(status):
    with pytest.raises(Conflict) as caught:
        lock.lock(visit(status=status), R1, 1, NOW)
    assert caught.value.extra["code"] == "not_ended"


def test_the_same_lock_again_changes_nothing():
    change = lock.lock(locked_for(), R1, 1, NOW + timedelta(minutes=5))
    assert change.fields == {} and change.locked


@pytest.mark.parametrize(("report_id", "version"), [(R1, 2), (R2, 1)])
def test_another_report_version_cannot_take_a_locked_visit(report_id, version):
    with pytest.raises(Conflict) as caught:
        lock.lock(locked_for(), report_id, version, NOW)
    assert caught.value.extra["code"] == "locked_by_another_report"


def test_the_holder_unlocks_the_visit():
    change = lock.unlock(locked_for(), R1, 1)
    assert not change.locked
    assert change.fields == {"locked": False, "locked_for": None, "locked_at": None}


def test_a_late_unlock_of_an_old_version_leaves_a_newer_lock_alone():
    change = lock.unlock(locked_for(R1, 2), R1, 1)
    assert change.fields == {} and change.locked


def test_unlocking_a_visit_that_is_not_locked_changes_nothing():
    change = lock.unlock(visit(), R1, 1)
    assert change.fields == {} and not change.locked


def test_a_visit_without_the_lock_fields_is_not_locked():
    assert lock.holder({"status": "ended"}) is None
    assert lock.holder(locked_for()) == (R1, 1)


@pytest.mark.req("RPT-6")
def test_finalized_sets_the_visit_report_fields():
    assert lock.finalized(visit(), R1, 1, NOW) == {
        "report_status": "final", "report_id": R1, "report_version": 1,
        "report_finalized_at": NOW,
    }


def test_finalized_ignores_an_older_or_repeated_version():
    final = visit(report_status="final", report_version=2, report_id=R1)
    assert lock.finalized(final, R1, 1, NOW) == {}
    assert lock.finalized(final, R1, 2, NOW) == {}
    assert lock.finalized(final, R1, 3, NOW)["report_version"] == 3


@pytest.mark.req("RPT-6")
def test_reopened_makes_the_report_a_draft_again():
    final = visit(report_status="final", report_version=1, report_id=R1, report_finalized_at=NOW)
    assert lock.reopened(final, R1, 2) == {
        "report_status": "draft", "report_id": R1, "report_version": 2,
        "report_finalized_at": None,
    }


def test_reopened_ignores_an_older_or_repeated_version():
    draft = visit(report_status="draft", report_version=2)
    assert lock.reopened(draft, R1, 2) == {}
    assert lock.reopened(draft, R1, 1) == {}


def test_a_late_finalized_does_not_undo_a_reopen():
    # final v1 -> reopened as v2 (draft); a redelivered `report.finalized` for v1 arrives last
    draft = visit(report_status="draft", report_version=2)
    assert lock.finalized(draft, R1, 1, NOW) == {}
