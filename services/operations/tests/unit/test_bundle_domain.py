"""The field bundle's rules (W13-9): which visits are prepared, by whom, and the record kept."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mms_common.errors import Conflict, Forbidden

from app.domain.visits import bundle as rules

AT = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)


def entry(user: str = "u1", device: str = "d1", at: datetime = AT):
    return rules.prepared_entry(user_id=user, user_name=user.upper(), device_id=device, at=at)


@pytest.mark.parametrize("status", ["planned", "started"])
def test_a_planned_or_started_visit_can_be_prepared(status):
    rules.check_preparable({"status": status})


@pytest.mark.parametrize("status", ["ended", "cancelled"])
def test_an_ended_or_cancelled_visit_cannot(status):
    with pytest.raises(Conflict) as caught:
        rules.check_preparable({"status": status})
    assert caught.value.code == "visit_not_preparable"


def test_the_people_attending_and_admins_prepare():
    visit = {"staff_ids": ["u1", "u2"]}
    rules.check_attending("u1", False, visit)
    rules.check_attending("u9", True, visit)
    with pytest.raises(Forbidden, match="people attending"):
        rules.check_attending("u9", False, visit)


def test_the_same_person_and_phone_has_one_entry_the_newest():
    later = datetime(2026, 10, 23, tzinfo=UTC)
    merged = rules.merge_prepared([entry()], entry(at=later))
    assert merged == [entry(at=later)]


def test_another_phone_or_person_adds_an_entry():
    merged = rules.merge_prepared([entry()], entry(device="d2"))
    merged = rules.merge_prepared(merged, entry(user="u2"))
    assert [(e["user_id"], e["device_id"]) for e in merged] == [
        ("u1", "d1"), ("u1", "d2"), ("u2", "d1")]


def test_only_the_newest_ten_are_kept():
    merged: list = []
    for n in range(rules.PREPARED_LIMIT + 3):
        merged = rules.merge_prepared(merged, entry(device=f"d{n}"))
    assert len(merged) == rules.PREPARED_LIMIT
    assert merged[-1]["device_id"] == f"d{rules.PREPARED_LIMIT + 2}"
    assert merged[0]["device_id"] == "d3"
