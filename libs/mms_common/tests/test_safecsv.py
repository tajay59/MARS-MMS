"""CSV cells that a spreadsheet will not run as formulas (W19-3)."""

from datetime import UTC, datetime

import pytest

from mms_common.safecsv import BOM, rows, safe_cell


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_a_cell_that_starts_like_a_formula_is_defused(start):
    assert safe_cell(f"{start}SUM(A1)") == f"'{start}SUM(A1)"


def test_ordinary_values_pass_through():
    assert safe_cell("Devon Clarke") == "Devon Clarke"
    assert safe_cell(None) == ""
    assert safe_cell(42) == "42"
    assert safe_cell("a=b") == "a=b"  # only the first character matters


def test_a_time_is_iso_utc():
    assert safe_cell(datetime(2026, 10, 28, 14, 38, 12, tzinfo=UTC)) == "2026-10-28T14:38:12.000Z"


def test_a_negative_number_is_defused_too():
    # Text from a user and a number look the same once written: err on the safe side.
    assert safe_cell("-5") == "'-5"


def test_the_file_starts_with_a_byte_order_mark_and_quotes_properly():
    out = "".join(rows(["when", "who"], [["x", 'say "hi", ok'], ["y", "=1+1"]]))
    assert out.startswith(BOM + "when,who\r\n")
    assert 'x,"say ""hi"", ok"\r\n' in out
    assert "y,'=1+1\r\n" in out
