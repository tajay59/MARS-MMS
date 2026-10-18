"""Builds operations' events (TRD §8.3, §8.4) and writes them to the outbox in the caller's
transaction (rule 2). The `audit` block holds before/after views of the changed record."""

from __future__ import annotations

from typing import Any

from mms_common import outbox
from mms_common.events import Actor, Envelope, Resource
from mms_common.events import operations as ev
from mms_common.ids import new_id
from mms_common.time import Clock
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

SOURCE = "operations"

STATION_FIELDS = (
    "code", "name", "type", "owner_org_id", "country", "time_zone", "region", "location",
    "elevation_m", "parameters", "logger", "comms", "power", "install_date", "status",
    "access_notes",
)
MODEL_FIELDS = ("kind", "manufacturer", "model", "parameters", "default_calibration_interval_days")
UNIT_FIELDS = (
    "model_id", "serial", "status", "current_station_id", "current_parameter",
    "calibration_interval_days", "last_calibrated_at", "calibration_due_at", "needs_review",
    "flags", "notes",
)


def view(doc: dict[str, Any] | None, fields: tuple[str, ...]) -> dict[str, Any] | None:
    return None if doc is None else {k: doc.get(k) for k in fields}


def station_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "station_id": doc["_id"], "code": doc["code"], "name": doc["name"],
        "org_id": doc["owner_org_id"], "country": doc["country"], "status": doc["status"],
        "type": doc.get("type"), "time_zone": doc.get("time_zone"),
    }


def model_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": doc["_id"], "kind": doc["kind"], "manufacturer": doc["manufacturer"],
        "model": doc["model"], "parameters": list(doc.get("parameters", [])),
        "default_calibration_interval_days": doc.get("default_calibration_interval_days"),
    }


def unit_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": doc["_id"], "serial": doc["serial"], "model_id": doc["model_id"],
        "status": doc["status"], "needs_review": bool(doc.get("needs_review")),
        "current_station_id": doc.get("current_station_id"),
        "calibration_due_at": doc.get("calibration_due_at"),
    }


def calibration_data(doc: dict[str, Any], due_at: Any) -> dict[str, Any]:
    return {
        "calibration_id": doc["_id"], "unit_id": doc["sensor_unit_id"],
        "station_id": doc.get("station_id"), "method": doc["method"], "at": doc["at"],
        "result": doc["result"], "due_at": due_at,
    }


def unit_key(unit: dict[str, Any]) -> str:
    """A unit at a station is keyed by the station (TRD §8.1); one in stock by itself."""
    return str(unit.get("current_station_id") or unit["_id"])


class Emitter:
    """One per request (or import run): carries the actor, correlation ID and clock."""

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

    async def station(
        self, model: type[BaseModel], doc: dict[str, Any], session: AsyncClientSession, *,
        before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        type_ = "station.created" if model is ev.StationCreated else "station.updated"
        return await self.emit(
            model(**station_data(doc), **extra), type_=type_, key=doc["_id"],
            resource=("station", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc["owner_org_id"], session=session,
            before=view(before, STATION_FIELDS), after=view(doc, STATION_FIELDS),
        )

    async def sensor_model(
        self, model: type[BaseModel], doc: dict[str, Any], session: AsyncClientSession, *,
        before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        type_ = "sensor_model.created" if model is ev.SensorModelCreated else "sensor_model.updated"
        return await self.emit(
            model(**model_data(doc), **extra), type_=type_, key=doc["_id"],
            resource=("sensor_model", doc["_id"]), aggregate_version=doc["version"],
            org_id=None, session=session,
            before=view(before, MODEL_FIELDS), after=view(doc, MODEL_FIELDS),
        )

    async def unit(
        self, model: type[BaseModel], doc: dict[str, Any], session: AsyncClientSession, *,
        before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        type_ = "sensor_unit.created" if model is ev.SensorUnitCreated else "sensor_unit.updated"
        return await self.emit(
            model(**unit_data(doc), **extra), type_=type_, key=unit_key(doc),
            resource=("sensor_unit", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc.get("current_org_id"), session=session,
            before=view(before, UNIT_FIELDS), after=view(doc, UNIT_FIELDS),
        )

    async def installation(
        self, model: type[BaseModel], installation: dict[str, Any], unit: dict[str, Any],
        session: AsyncClientSession, *, before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        """`sensor.installed` / `sensor.removed`, versioned by the unit they changed."""
        removed = model is ev.SensorRemoved
        data = model(
            installation_id=installation["_id"], unit_id=unit["_id"], serial=unit["serial"],
            model_id=unit["model_id"], station_id=installation["station_id"],
            parameter=installation.get("parameter"),
            at=installation["removed_at"] if removed else installation["installed_at"],
            unit_status=unit["status"], visit_id=installation.get(
                "removed_visit_id" if removed else "installed_visit_id"
            ),
            action_id=installation.get("source_action_id"),
            **extra,
        )
        return await self.emit(
            data, type_="sensor.removed" if removed else "sensor.installed",
            key=installation["station_id"], resource=("sensor_unit", unit["_id"]),
            aggregate_version=unit["version"], org_id=installation["org_id"], session=session,
            before=view(before, UNIT_FIELDS), after=view(unit, UNIT_FIELDS),
        )

    async def calibration(
        self, doc: dict[str, Any], unit: dict[str, Any], session: AsyncClientSession
    ) -> Envelope:
        return await self.emit(
            ev.CalibrationRecorded(**calibration_data(doc, unit.get("calibration_due_at"))),
            type_="calibration.recorded",
            key=str(doc.get("station_id") or unit["_id"]),
            resource=("calibration", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc.get("org_id"), session=session,
            after={k: doc.get(k) for k in ("sensor_unit_id", "station_id", "at", "method",
                                           "reference_instrument", "readings", "result",
                                           "certificate_media_id", "performed_by", "notes")},
        )


__all__ = [
    "Emitter", "calibration_data", "ev", "model_data", "station_data", "unit_data", "view",
]
