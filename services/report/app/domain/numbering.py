"""Report numbers (PRD RPT-10, Q1). One function, so the format can change in one place.

A visit report's number is the visit's own reference (`VR-2026-0042-02`: request 42, visit 2); the
version is separate ("v1") and both appear in the file name.
"""

from __future__ import annotations


def visit_report_number(visit_ref: str) -> str:
    return visit_ref


def file_name(number: str, version: int, *, draft: bool) -> str:
    return f"{number}-v{version}{'-draft' if draft else ''}.pdf"
