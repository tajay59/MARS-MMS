"""Audit record mapping and chain maths (no I/O), and the AUD-1 completeness contract."""

from datetime import UTC, datetime

import pytest
from mms_common.events import SCHEMAS, Actor, Envelope, Resource

from app.domain.audit import (
    AUD1,
    GENESIS,
    NOTIFICATION_ONLY,
    all_aud1_types,
    audited,
    canonical,
    chain,
    first_break,
    to_record,
)

AT = datetime(2026, 10, 17, 9, 0, 0, 987654, tzinfo=UTC)


def envelope(**over) -> Envelope:
    fields = dict(
        event_id="e1", type="user.updated", occurred_at=AT, source="auth", key="u",
        aggregate_version=2, actor=Actor(user_id="a", name="Admin", roles=["admin"]),
        resource=Resource(type="user", id="u"), org_id=None, correlation_id="c",
        audit={"before": {"name": "A"}, "after": {"name": "B"}}, data={"user_id": "u"},
    )
    fields.update(over)
    return Envelope(**fields)


def test_record_fields_follow_aud2():
    record = to_record(envelope(), AT)
    assert record["_id"] == "e1"
    assert record["at"] == AT.replace(microsecond=987000)
    assert record["action"] == "user.updated"
    assert record["actor"]["name"] == "Admin"
    assert (record["before"], record["after"]) == ({"name": "A"}, {"name": "B"})
    assert record["metadata"] == {"user_id": "u"}


def test_canonical_form_ignores_key_order_and_the_hash():
    a = {"b": 1, "a": {"y": 2, "x": 1}, "hash": "zzz"}
    b = {"a": {"x": 1, "y": 2}, "b": 1}
    assert canonical(a) == canonical(b) == b'{"a":{"x":1,"y":2},"b":1}'


def test_naive_and_aware_utc_times_hash_the_same():
    aware = {"at": datetime(2026, 1, 1, tzinfo=UTC)}
    naive = {"at": datetime(2026, 1, 1)}
    assert canonical(aware) == canonical(naive)


def test_chain_links_and_detects_breaks():
    records = []
    prev = GENESIS
    for n in range(1, 5):
        linked = chain(to_record(envelope(event_id=f"e{n}"), AT), n, prev)
        records.append(linked)
        prev = linked["hash"]
    assert first_break(records, 1, GENESIS) is None
    records[2]["metadata"] = {"user_id": "someone else"}
    assert first_break(records, 1, GENESIS) == 3
    assert first_break(records[:2] + records[3:], 1, GENESIS) == 3  # a gap


def test_notification_only_events_are_skipped():
    assert not audited("calibration.due_digest")
    assert audited("request.approved")


def test_aud1_lists_no_notification_only_event():
    assert not set(all_aud1_types()) & NOTIFICATION_ONLY


# Event types of the producers built so far: auth (Phase 1), operations' stations module
# (Phase 2). Extend as each producer is built.
BUILT_PREFIXES = (
    "auth.", "user.", "org.", "branding.",
    "station.", "sensor_model.", "sensor_unit.", "sensor.", "calibration.recorded",
    "calibration.voided",
)


@pytest.mark.req("AUD-1")
def test_every_aud1_action_built_so_far_has_an_event_schema():
    """TRD §12 completeness: each AUD-1 action maps to event types, and every type from a
    service that exists has a registered schema. Extend as each producer is built."""
    built_sources = BUILT_PREFIXES
    for action, types in AUD1.items():
        assert types, action
        for type_ in types:
            if type_.startswith(built_sources):
                assert (type_, 1) in SCHEMAS, f"{action}: {type_} has no schema"


def test_every_built_event_is_audited():
    for type_, _ in SCHEMAS:
        if type_.startswith(BUILT_PREFIXES):
            assert type_ in set(all_aud1_types()), f"{type_} is not mapped to an AUD-1 action"
