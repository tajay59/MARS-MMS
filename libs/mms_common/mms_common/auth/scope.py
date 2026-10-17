"""Organization scoping for the repository layer (CLAUDE.md rule 3, TRD §6.3).

Every repo read for a client goes through `scoped`, which forces the client's own org onto
the query. A value the caller put in that field is overwritten, never trusted, so endpoint
code cannot widen the result. Out-of-scope records then simply aren't found (404, rule 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mms_common.auth.principal import User

ORG = "org_id"
STATION_OWNER = "owner_org_id"  # stations
UNIT_HOLDER = "current_org_id"  # sensor units

_NOTHING: dict[str, Any] = {"$in": []}  # matches no document


def scoped(user: User, query: Mapping[str, Any] | None = None, field: str = ORG) -> dict[str, Any]:
    merged = dict(query or {})
    if user.is_client:
        merged[field] = user.org_id if user.org_id else _NOTHING
    return merged
