"""Label sheet rules with no I/O (QR-1, QR-6)."""

from __future__ import annotations

import pytest
from mms_common.errors import ValidationFailed

from app.domain import labels


def make(n: int) -> list[labels.Label]:
    return [labels.Label(f"id{i}", f"C{i}", f"Station {i}", "Org", f"u{i}") for i in range(n)]


def test_the_qr_holds_the_app_address_and_the_token_only():
    assert labels.scan_url("https://mms.example/", "abc_-123") == "https://mms.example/s/abc_-123"
    assert labels.scan_url("https://mms.example", "t") == "https://mms.example/s/t"


@pytest.mark.parametrize(("count", "pages"), [(0, 0), (1, 1), (10, 1), (11, 2), (200, 20)])
def test_ten_labels_to_a_page(count, pages):
    result = labels.paginate(make(count))
    assert len(result) == pages
    assert sum(len(p) for p in result) == count
    assert all(len(p) <= labels.PER_PAGE for p in result)


def test_labels_keep_their_order():
    flat = [label.code for page in labels.paginate(make(25)) for label in page]
    assert flat == [f"C{i}" for i in range(25)]


@pytest.mark.parametrize("value", ["+1 876 555 0100", "(876) 555-0100", "8765550100"])
def test_phones_that_are_fine(value):
    assert labels.check_phone(value) == value


@pytest.mark.parametrize("value", [None, "", "   "])
def test_no_phone_is_allowed(value):
    assert labels.check_phone(value) is None


@pytest.mark.parametrize("value", ["call me", "<script>", "+", "12", "1" * 40])
def test_phones_that_are_not(value):
    with pytest.raises(ValidationFailed):
        labels.check_phone(value)
