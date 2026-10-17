"""Builds auth's events (TRD §8.3, §8.4) and writes them to the outbox in the caller's
transaction (rule 2). The `audit` block holds safe before/after views: never a password
hash or a token."""

from __future__ import annotations

from typing import Any

from mms_common import outbox
from mms_common.events import Actor, Envelope, Resource
from mms_common.events import auth as ev
from mms_common.ids import new_id
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

SOURCE = "auth"
USER_FIELDS = ("email", "name", "phone", "roles", "status", "org_id", "time_zone", "theme")
ORG_FIELDS = ("name", "country", "contact_email", "phone", "address", "status")


def user_view(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if doc is None else {k: doc.get(k) for k in USER_FIELDS}


def org_view(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if doc is None else {k: doc.get(k) for k in ORG_FIELDS}


def user_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": doc["_id"],
        "email": doc["email"],
        "name": doc["name"],
        "roles": list(doc["roles"]),
        "status": doc["status"],
        "org_id": doc.get("org_id"),
    }


def org_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "org_id": doc["_id"],
        "name": doc["name"],
        "country": doc["country"],
        "status": doc["status"],
    }


class Emitter:
    """One per request: carries the actor, correlation ID and clock into every event."""

    def __init__(
        self,
        db: AsyncDatabase[dict[str, Any]],
        clock: Clock,
        actor: Actor,
        correlation_id: str | None,
    ) -> None:
        self._db = db
        self._clock = clock
        self.actor = actor
        self._correlation_id = correlation_id

    async def emit(
        self,
        data: BaseModel,
        *,
        type_: str,
        key: str,
        resource: tuple[str, str],
        aggregate_version: int,
        org_id: str | None,
        session: AsyncClientSession,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> Envelope:
        envelope = Envelope(
            event_id=new_id(),
            type=type_,
            occurred_at=self._clock.now(),
            source=SOURCE,
            key=key,
            aggregate_version=aggregate_version,
            actor=self.actor,
            org_id=org_id,
            resource=Resource(type=resource[0], id=resource[1]),
            correlation_id=self._correlation_id,
            audit={"before": before, "after": after},
            data=data.model_dump(mode="json"),
        )
        await outbox.add(self._db["outbox"], envelope, session=session, clock=self._clock)
        return envelope

    async def user(
        self,
        type_: str,
        model: type[BaseModel],
        doc: dict[str, Any],
        session: AsyncClientSession,
        *,
        before: dict[str, Any] | None = None,
        **extra: Any,
    ) -> Envelope:
        """A `user.*` event. Its data carries the directory fields (TRD §5.5)."""
        return await self.emit(
            model(**user_data(doc), **extra),
            type_=type_,
            key=doc["_id"],
            resource=("user", doc["_id"]),
            aggregate_version=doc["version"],
            org_id=doc.get("org_id"),
            session=session,
            before=user_view(before),
            after=user_view(doc),
        )

    async def org(
        self,
        type_: str,
        model: type[BaseModel],
        doc: dict[str, Any],
        session: AsyncClientSession,
        *,
        before: dict[str, Any] | None = None,
        **extra: Any,
    ) -> Envelope:
        return await self.emit(
            model(**org_data(doc), **extra),
            type_=type_,
            key=doc["_id"],
            resource=("organization", doc["_id"]),
            aggregate_version=doc["version"],
            org_id=doc["_id"],
            session=session,
            before=org_view(before),
            after=org_view(doc),
        )

    async def security(
        self,
        data: BaseModel,
        *,
        type_: str,
        user: dict[str, Any] | None,
        email_hash: str,
        session: AsyncClientSession,
    ) -> Envelope:
        """An `auth.*` event. A failed login for an unknown email is keyed by its hash."""
        subject = user["_id"] if user else email_hash
        return await self.emit(
            data,
            type_=type_,
            key=subject,
            resource=("user", subject),
            aggregate_version=user["version"] if user else 0,
            org_id=user.get("org_id") if user else None,
            session=session,
        )


__all__ = ["Emitter", "ev", "org_view", "user_data", "user_view"]
