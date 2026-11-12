"""Second factor (W22): `users.totp`, `users.recovery_codes` and `users.mfa_grace_until` are
optional fields on the `users` documents, so nothing is written to existing records. A person who
needs a factor and has no `mfa_grace_until` gets their setup window on their next sign-in. This
migration only names the change, so it appears in `_migrations` and the rollback guard sees it."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["users"].create_index("roles")
