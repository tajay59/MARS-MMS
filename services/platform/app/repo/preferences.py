"""`preferences`: each person's email choices (PRD NOT-4), one document per user."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.domain.preferences import from_storage, storage_key

Db = AsyncDatabase[dict[str, Any]]


def col(db: Db) -> Any:
    return db["preferences"]


async def email_choices(db: Db, user_id: str) -> dict[str, bool]:
    """What the person chose; a type they never touched is not in it (its default applies)."""
    doc = await col(db).find_one({"_id": user_id})
    out: dict[str, bool] = {}
    for stored, value in (doc or {}).get("email", {}).items():
        if (key := from_storage(stored)) is not None:
            out[key] = bool(value)
    return out


async def save_email_choices(
    db: Db, user_id: str, choices: dict[str, bool], now: datetime
) -> dict[str, bool]:
    """Merge `choices` into the stored ones (typed keys only: rule 12)."""
    await col(db).update_one(
        {"_id": user_id},
        {"$set": {**{f"email.{storage_key(k)}": v for k, v in choices.items()}, "updated_at": now}},
        upsert=True,
    )
    return await email_choices(db, user_id)
