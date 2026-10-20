"""`derive_status` (TRD §3.2.2, PRD §5.1, ADR-17): examples for each rule, then property tests
that hold for every list of visits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.requests.derive import VisitFacts, derive_status
from app.domain.requests.state import DERIVED, Status

T0 = datetime(2026, 10, 1, 8, tzinfo=UTC)


def planned() -> VisitFacts:
    return VisitFacts("planned")


def started() -> VisitFacts:
    return VisitFacts("started")


def ended(hours: int = 0, *, more: bool = False, final: bool = True,
          finalized_hours: int | None = None) -> VisitFacts:
    return VisitFacts(
        "ended", ended_at=T0 + timedelta(hours=hours), additional_visit_required=more,
        report_status="final" if final else "draft",
        report_finalized_at=T0 + timedelta(hours=finalized_hours if finalized_hours is not None
                                           else hours) if final else None,
    )


def cancelled() -> VisitFacts:
    return VisitFacts("cancelled")


# --- One example for each rule ----------------------------------------------------------------


def test_no_visits_is_assigned():
    assert derive_status(Status.ASSIGNED, []) is Status.ASSIGNED


def test_a_visit_under_way_is_in_progress_even_beside_a_planned_one():
    assert derive_status(Status.SCHEDULED, [started(), planned()]) is Status.IN_PROGRESS


def test_a_planned_visit_is_scheduled():
    assert derive_status(Status.ASSIGNED, [planned()]) is Status.SCHEDULED
    assert derive_status(Status.ASSIGNED, [ended(), planned()]) is Status.SCHEDULED


def test_cancelled_visits_do_not_count():
    assert derive_status(Status.SCHEDULED, [cancelled()]) is Status.ASSIGNED
    assert derive_status(Status.SCHEDULED, [cancelled(), planned()]) is Status.SCHEDULED


def test_the_last_visit_asking_for_another_sends_it_back_to_assigned():
    assert derive_status(Status.IN_PROGRESS, [ended(1), ended(2, more=True)]) is Status.ASSIGNED
    # ...but only the most recent one counts
    assert derive_status(Status.IN_PROGRESS, [ended(1, more=True), ended(2)]) \
        is Status.CLIENT_REVIEW


def test_visits_that_ended_together_need_another_if_any_of_them_asks():
    assert derive_status(Status.ASSIGNED, [ended(1, more=True), ended(1)]) is Status.ASSIGNED
    assert derive_status(Status.ASSIGNED, [ended(1), ended(1, more=True)]) is Status.ASSIGNED


def test_a_report_that_is_not_final_keeps_it_in_progress():
    assert derive_status(Status.ASSIGNED, [ended(final=False)]) is Status.IN_PROGRESS
    assert derive_status(Status.ASSIGNED, [ended(1), ended(2, final=False)]) is Status.IN_PROGRESS


def test_every_report_final_and_no_more_visits_is_client_review():
    assert derive_status(Status.IN_PROGRESS, [ended(1), ended(2)]) is Status.CLIENT_REVIEW


def test_a_reopened_report_in_client_review_goes_back_to_in_progress():
    visits = [ended(1, final=False)]
    assert derive_status(Status.CLIENT_REVIEW, visits) is Status.IN_PROGRESS


def test_after_a_rejection_it_stays_assigned_until_something_new_happens():
    rejected = T0 + timedelta(hours=10)
    old = [ended(1)]
    assert derive_status(Status.ASSIGNED, old, rework_since=rejected) is Status.ASSIGNED
    # a new visit ended after the rejection
    assert derive_status(Status.ASSIGNED, [*old, ended(11)], rework_since=rejected) \
        is Status.CLIENT_REVIEW
    # or a corrected report was finalized after it
    corrected = [ended(1, finalized_hours=11)]
    assert derive_status(Status.ASSIGNED, corrected, rework_since=rejected) \
        is Status.CLIENT_REVIEW


@pytest.mark.parametrize("status", [s for s in Status if s not in DERIVED])
def test_outside_the_derived_range_nothing_changes(status):
    assert derive_status(status, [started(), planned(), ended()]) is status


# --- Properties -------------------------------------------------------------------------------

visit_facts = st.one_of(
    st.just(planned()), st.just(started()), st.just(cancelled()),
    st.builds(
        lambda h, more, final, fin: ended(h, more=more, final=final, finalized_hours=fin),
        st.integers(0, 200), st.booleans(), st.booleans(), st.integers(0, 200),
    ),
)
visits = st.lists(visit_facts, max_size=8)
rework = st.one_of(st.none(), st.integers(0, 200).map(lambda h: T0 + timedelta(hours=h)))


@given(visits, rework)
def test_the_answer_is_always_one_of_the_four_derived_statuses(items, since):
    assert derive_status(Status.ASSIGNED, items, since) in DERIVED


@given(visits, rework)
def test_the_answer_does_not_depend_on_the_current_derived_status(items, since):
    answers = {derive_status(current, items, since) for current in DERIVED}
    assert len(answers) == 1


@given(visits, rework)
def test_the_order_of_the_visits_does_not_matter(items, since):
    assert derive_status(Status.ASSIGNED, items, since) \
        == derive_status(Status.ASSIGNED, list(reversed(items)), since)


@given(visits, rework)
def test_cancelled_visits_never_change_the_answer(items, since):
    assert derive_status(Status.ASSIGNED, [*items, cancelled(), cancelled()], since) \
        == derive_status(Status.ASSIGNED, items, since)


@given(visits, rework)
def test_a_visit_under_way_always_wins(items, since):
    assert derive_status(Status.ASSIGNED, [*items, started()], since) is Status.IN_PROGRESS


@given(visits, rework)
def test_planned_work_is_scheduled_unless_a_visit_is_under_way(items, since):
    got = derive_status(Status.ASSIGNED, [*items, planned()], since)
    assert got in (Status.SCHEDULED, Status.IN_PROGRESS)
    assert (got is Status.IN_PROGRESS) == any(v.status == "started" for v in items)


@given(visits, rework)
def test_client_review_needs_every_ended_report_final_and_no_open_visit(items, since):
    if derive_status(Status.ASSIGNED, items, since) is Status.CLIENT_REVIEW:
        ended_visits = [v for v in items if v.status == "ended"]
        assert ended_visits
        assert all(v.report_status == "final" for v in ended_visits)
        assert not any(v.status in ("planned", "started") for v in items)
        latest = max(v.ended_at or T0 for v in ended_visits)
        assert not any(v.additional_visit_required for v in ended_visits if v.ended_at == latest)


@given(visits)
def test_without_a_rejection_the_rework_rule_never_applies(items):
    """`rework_since=None` and a rejection long before any visit give the same answer."""
    assert derive_status(Status.ASSIGNED, items, None) \
        == derive_status(Status.ASSIGNED, items, T0 - timedelta(days=1000))
