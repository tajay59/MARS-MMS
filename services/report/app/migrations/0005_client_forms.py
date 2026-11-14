"""Client form reports (W18-10): a report is found by its client report, and one version of a
subject exists once (so a repeated `client_report.submitted` can never make two)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["reports"].create_index(
        [("subject_ref", 1), ("version", 1)], unique=True, name="one_version_of_a_subject")
    await db["reports"].create_index(
        [("client_report_id", 1)],
        partialFilterExpression={"client_report_id": {"$type": "string"}},
        name="client_report_id",
    )
