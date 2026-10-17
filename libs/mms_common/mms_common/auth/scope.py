"""Organization scoping for the repository layer (CLAUDE.md rule 3, TRD §6.3).

Every repo read for a client goes through `scoped`, which adds the client's own org to the
query. If the query already filters on that field, both conditions must hold, so endpoint
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
    if not user.is_client:
        return merged
    own: Any = user.org_id if user.org_id else _NOTHING
    if field in merged:
        return {"$and": [merged, {field: own}]}
    merged[field] = own
    return merged
