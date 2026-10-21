"""Pushing to open browsers (TRD §3.5, §13.4): every message for a person goes to the Redis
channel `ws:user:{id}`, and each platform instance forwards it to that person's sockets.

Redis pub/sub is fire and forget. That is fine: a notification is already stored before it is
pushed, and a browser that missed one asks `GET /notifications?after=` when it reconnects
(NOT-2). A push that fails is logged and never fails the event."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mms_common.logging import get_logger
from redis.asyncio import Redis

log = get_logger(__name__)


def channel(user_id: str) -> str:
    return f"ws:user:{user_id}"


def notification_message(doc: dict[str, Any]) -> dict[str, Any]:
    return {"type": "notification", "data": out(doc)}


def entity_message(entity_id: str, status: str, kind: str) -> dict[str, Any]:
    return {"type": "entity.updated", "entity": "request", "id": entity_id, "status": status,
            "kind": kind}


def out(doc: dict[str, Any]) -> dict[str, Any]:
    """A notification as the browser sees it (also the REST shape)."""
    created: datetime = doc["created_at"]
    return {
        "id": doc["_id"], "type": doc["type"], "title": doc["title"], "body": doc["body"],
        "link": doc["link"], "entity": doc["entity"], "read": doc["read_at"] is not None,
        "created_at": created.isoformat(),
    }


async def publish(redis: Redis, messages: list[tuple[str, dict[str, Any]]]) -> None:
    """`(user_id, message)` pairs. Best effort."""
    for user_id, message in messages:
        try:
            await redis.publish(channel(user_id), json.dumps(message))
        except Exception as exc:  # noqa: BLE001 - a push never fails the event
            log.warning("push_failed", error=f"{type(exc).__name__}: {exc}"[:200])
