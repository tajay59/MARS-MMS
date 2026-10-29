"""CSV that is safe to open in a spreadsheet (W19-3).

A cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is read as a formula by
Excel and Sheets, so a name or a note typed by a user could run one. Such a cell gets a leading
apostrophe. Files start with a byte order mark so Excel reads them as UTF-8.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from typing import Any

from mms_common.time import to_iso

BOM = "﻿"
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> str:
    """One cell as text: None is empty, times are ISO 8601 UTC, and a formula is defused."""
    if value is None:
        return ""
    text = to_iso(value) if isinstance(value, datetime) else str(value)
    if text.startswith(_DANGEROUS):
        return "'" + text
    return text


class Writer:
    """Writes one line at a time, for a file that is streamed."""

    def __init__(self) -> None:
        self._buffer = io.StringIO()
        self._writer = csv.writer(self._buffer, lineterminator="\r\n")

    def line(self, cells: Sequence[Any]) -> str:
        self._writer.writerow([safe_cell(cell) for cell in cells])
        out = self._buffer.getvalue()
        self._buffer.seek(0)
        self._buffer.truncate()
        return out

    def header(self, cells: Sequence[str]) -> str:
        """The first line, after the byte order mark."""
        return BOM + self.line(cells)


def rows(header: Sequence[str], body: Iterable[Sequence[Any]]) -> Iterator[str]:
    """A whole file in pieces: the header first, then one string per row."""
    writer = Writer()
    yield writer.header(header)
    for row in body:
        yield writer.line(row)
