"""The real-time channel (PRD NOT-1, NOT-5; TRD §3.5, §13.4).

    client:  {"type": "auth", "token": "<access token>"}      within 5 s of connecting
    server:  {"type": "ready"}
    server:  {"type": "notification", "data": {...}}
    server:  {"type": "entity.updated", "entity": "request", "id": ..., "status": ..., "kind": ...}
    server:  {"type": "ping"} every 25 s            client: anything back (a pong) is fine
    client:  {"type": "auth", "token": ...} again, any time before the token ends, to stay on

A socket lives as long as its token. The token is checked again at every heartbeat (expiry and
the revocation list) and the socket closes with 4401 when that fails, so a disabled account is
cut off within one heartbeat. The browser then refreshes its token and reconnects. The token is
never in the address (it would reach the logs). Nothing here is the system of record: a missed
message is found again through `GET /api/v1/notifications?after=`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from mms_common.auth import Authenticator, User
from mms_common.errors import AppError
from redis.asyncio import Redis

from app import realtime

router = APIRouter()

AUTH_WAIT_S = 5
UNAUTHENTICATED = 4401
BAD_MESSAGE = 4400


async def _auth(authenticator: Authenticator, token: Any) -> tuple[User, int] | None:
    if not isinstance(token, str):
        return None
    try:
        return await authenticator.user_with_expiry(token)
    except AppError:
        return None


@router.websocket("/ws")
async def socket(websocket: WebSocket) -> None:
    app = websocket.app
    authenticator: Authenticator = app.state.authenticator
    redis: Redis = app.state.redis
    heartbeat_s: float = app.state.settings.ws_heartbeat_s
    await websocket.accept()

    try:
        first = json.loads(await asyncio.wait_for(websocket.receive_text(), AUTH_WAIT_S))
    except (TimeoutError, ValueError, WebSocketDisconnect):
        await _close(websocket, UNAUTHENTICATED)
        return
    asked = first if isinstance(first, dict) and first.get("type") == "auth" else {}
    found = await _auth(authenticator, asked.get("token"))
    if found is None:
        await _close(websocket, UNAUTHENTICATED)
        return
    user, _ = found
    token: str = asked["token"]
    # Subscribe before saying "ready", so nothing sent after the browser hears it can be missed
    pubsub = redis.pubsub()
    await pubsub.subscribe(realtime.channel(user.id))
    await websocket.send_text(json.dumps({"type": "ready"}))

    async def forward() -> None:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None and message.get("type") == "message":
                data = message["data"]
                await websocket.send_text(data.decode() if isinstance(data, bytes) else data)

    async def listen() -> None:
        nonlocal token
        while True:
            try:
                message = json.loads(await websocket.receive_text())
            except WebSocketDisconnect:
                return  # the browser went away
            except ValueError:
                await _close(websocket, BAD_MESSAGE)
                return
            if isinstance(message, dict) and message.get("type") == "auth":
                again = await _auth(authenticator, message.get("token"))
                if again is None or again[0].id != user.id:
                    await _close(websocket, UNAUTHENTICATED)
                    return
                token = message["token"]

    async def beat() -> None:
        while True:
            await asyncio.sleep(heartbeat_s)
            if await _auth(authenticator, token) is None:
                await _close(websocket, UNAUTHENTICATED)
                return
            await websocket.send_text(json.dumps({"type": "ping"}))

    tasks = [asyncio.create_task(c()) for c in (forward, listen, beat)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]


async def _close(websocket: WebSocket, code: int) -> None:
    with contextlib.suppress(Exception):
        await websocket.close(code=code)
