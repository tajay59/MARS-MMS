"""ClamAV's VERSION answer gives the age of its signatures (TRD §16.5: older than 3 days is an
alert)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.repo.scanner import parse_signature_date


def test_the_build_time_is_the_third_part_of_the_answer():
    reply = b"ClamAV 1.4.3/27850/Wed Oct 28 08:30:00 2026\0"
    assert parse_signature_date(reply) == datetime(2026, 10, 28, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize("reply", [b"", b"ClamAV 1.4.3\0", b"ClamAV 1.4.3/27850/not a date\0"])
def test_an_answer_that_cannot_be_read_gives_nothing(reply):
    assert parse_signature_date(reply) is None
