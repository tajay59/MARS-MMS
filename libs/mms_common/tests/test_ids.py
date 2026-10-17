import uuid
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from mms_common.ids import IdGenerator, is_uuid7, new_id, seeded
from mms_common.time import ManualClock


def test_new_id_is_a_uuid7():
    value = new_id()
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    assert is_uuid7(value)


def test_embeds_the_clock_in_milliseconds():
    clock = ManualClock(datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC))
    value = IdGenerator(clock=clock).new()
    ms = uuid.UUID(value).int >> 80
    assert ms == int(clock.now().timestamp() * 1000)


def test_seeded_generators_repeat():
    a = [seeded(ManualClock(), seed=7).new() for _ in range(3)]
    b = [seeded(ManualClock(), seed=7).new() for _ in range(3)]
    assert a == b


@given(st.integers(min_value=2, max_value=200))
def test_ids_increase_even_within_one_millisecond(n):
    gen = seeded(ManualClock(), seed=1)  # clock never moves: worst case
    ids = [gen.new() for _ in range(n)]
    assert ids == sorted(ids)
    assert len(set(ids)) == n


def test_ids_stay_ordered_if_the_clock_steps_back():
    clock = ManualClock()
    gen = seeded(clock, seed=3)
    first = gen.new()
    clock.advance(seconds=-5)
    assert gen.new() > first


def test_pattern_rejects_other_versions():
    assert not is_uuid7(str(uuid.uuid4()))
    assert not is_uuid7("not-an-id")
