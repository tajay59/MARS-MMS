"""What `/sync` answers for each raised error, and the stop-per-visit rule (W14-2 to W14-5)."""

from __future__ import annotations

import pytest
from mms_common.errors import (
    AppError,
    Conflict,
    Forbidden,
    NotFound,
    RateLimited,
    ValidationFailed,
)

from app.domain import sync as rules


@pytest.mark.parametrize("code", ["not_owner", "not_editor", "visit_cancelled", "locked",
                                  "already_ended", "element_deleted", "not_attending"])
def test_a_conflict_or_refusal_with_a_known_code_is_a_conflict(code):
    for exc in (Conflict("no", code=code), Forbidden("no", code=code)):
        answer = rules.classify("op1", exc)
        assert answer.status == "conflict" and answer.code == code and not answer.retryable


def test_the_server_copy_travels_with_an_element_conflict():
    changed = Conflict("changed", code="element_changed", current={"id": "e1"})
    answer = rules.classify("op1", changed)
    assert answer.status == "conflict" and answer.current == {"id": "e1"}


def test_a_file_media_has_not_finished_is_asked_again_later():
    answer = rules.classify("op1", Conflict("wait", code="file_not_uploaded"))
    assert answer.status == "error" and answer.retryable


def test_a_failed_validation_is_a_permanent_error_the_person_sees():
    answer = rules.classify("op1", ValidationFailed("A title is needed", code="title_required"))
    assert (answer.status, answer.code, answer.retryable) == ("error", "title_required", False)


def test_something_gone_is_not_found_and_a_server_failure_is_retried():
    assert rules.classify("op1", NotFound()).code == "not_found"
    broken = rules.classify("op1", RuntimeError("boom"))
    assert (broken.status, broken.code, broken.retryable) == ("error", "try_again", True)
    down = rules.classify("op1", AppError("down"))
    assert down.retryable is True


def test_other_client_errors_are_permanent():
    answer = rules.classify("op1", RateLimited("slow down"))
    assert answer.status == "error" and not answer.retryable


def test_payload_versions():
    assert rules.stale_version("o", 1) is None
    newer = rules.stale_version("o", rules.CURRENT_VERSION + 1)
    assert newer and newer.code == "update_required" and newer.retryable
    older = rules.stale_version("o", 0)
    assert older and older.code == "unsupported_version" and not older.retryable


def test_a_failed_operation_stops_its_visit_and_no_other():
    batch = rules.Batch()
    batch.settle("v1", rules.Answer("a", "applied"))
    assert not batch.waits("v1")
    batch.settle("v1", rules.Answer("b", "conflict", code="not_owner"))
    batch.settle("v2", rules.Answer("c", "duplicate"))
    assert batch.waits("v1") and not batch.waits("v2")
    batch.settle("v3", rules.Answer("d", "error", code="try_again", retryable=True))
    assert batch.waits("v3")


def test_conflicts_are_grouped_by_visit_and_reason_for_one_notice_each():
    found = rules.conflicts_to_report([
        ("v1", "station.arrive", rules.Answer("a", "conflict", code="not_owner")),
        ("v1", "station.depart", rules.Answer("b", "conflict", code="not_owner")),
        ("v1", "element.create", rules.Answer("c", "conflict", code="locked")),
        ("v2", "visit.end", rules.Answer("d", "applied")),
        ("v2", "element.update", rules.Answer("e", "error", code="x")),
    ])
    assert found == {("v1", "not_owner"): ["station.arrive", "station.depart"],
                     ("v1", "locked"): ["element.create"]}
