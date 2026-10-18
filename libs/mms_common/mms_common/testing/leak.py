"""Client leak test (TP "Rule-enforcement tests", rule 6, D4).

Every response returned to a client token is walked. Staff appear to clients only as
`{id, name}`: an `email` or `phone` on any object other than the client's own user or org
is a leak. Some keys must never leave a service for anyone.
"""

from __future__ import annotations

from typing import Any

NEVER_SENT = frozenset(
    {"password_hash", "token_hash", "successor_enc", "private_key_ref", "private_key"}
)
CONTACT = frozenset({"email", "phone"})


def find_leaks(
    body: Any, *, own_ids: frozenset[str] = frozenset(), client: bool = True
) -> list[str]:
    """Paths of leaked fields in a JSON body. `own_ids`: the client's user and org IDs."""
    found: list[str] = []
    _walk(body, "$", own_ids, client, found)
    return found


def _walk(node: Any, path: str, own: frozenset[str], client: bool, found: list[str]) -> None:
    if isinstance(node, dict):
        for key in NEVER_SENT & node.keys():
            found.append(f"{path}.{key}")
        if client:
            node_id = node.get("id", node.get("_id"))
            if node_id not in own:
                found.extend(f"{path}.{key}" for key in CONTACT & node.keys())
            if node.get("internal") is True:
                found.append(f"{path} (internal)")
        for key, value in node.items():
            _walk(value, f"{path}.{key}", own, client, found)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, f"{path}[{i}]", own, client, found)
