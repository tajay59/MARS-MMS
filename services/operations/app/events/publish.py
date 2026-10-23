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

from app.domain.visits.elements import facts as element_facts

SOURCE = "operations"

STATION_FIELDS = (
    "code", "name", "type", "owner_org_id", "country", "time_zone", "region", "location",
    "elevation_m", "parameters", "logger", "comms", "power", "install_date", "status",
    "access_notes",
)
DOCUMENT_FIELDS = (
    "scope", "scope_id", "doc_type", "title", "version_label", "language", "description",
    "client_visible", "media_id", "supersedes_id", "is_current", "status",
)
MODEL_FIELDS = (
    "kind", "manufacturer", "model", "parameters", "default_calibration_interval_days", "specs",
)
REQUEST_FIELDS = (
    "ref", "org_id", "title", "description", "category", "priority", "station_ids", "status",
    "assigned_staff_ids", "denial_reason", "cancel_reason",
)
COMMENT_FIELDS = ("request_id", "author_id", "author_role", "body", "internal", "attachments")
VISIT_FIELDS = (
    "ref", "request_id", "status", "planned_start", "planned_end", "staff_ids", "lead_staff_id",
    "started_at", "ended_at", "additional_visit_required", "cancel_reason",
)
UNIT_FIELDS = (
    "model_id", "serial", "status", "current_station_id", "current_parameter",
    "calibration_interval_days", "last_calibrated_at", "calibration_due_at", "flags", "notes",
)
ELEMENT_FIELDS = (
    "visit_id", "station_id", "kind", "title", "description", "items", "priority", "shared",
    "completed_at", "request_ref", "config_version_ids", "deleted_at",
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
        "status": doc["status"], "current_station_id": doc.get("current_station_id"),
        "calibration_due_at": doc.get("calibration_due_at"),
    }


def calibration_data(doc: dict[str, Any], due_at: Any) -> dict[str, Any]:
    return {
        "calibration_id": doc["_id"], "unit_id": doc["sensor_unit_id"],
        "station_id": doc.get("station_id"), "method": doc["method"], "at": doc["at"],
        "result": doc["result"], "due_at": due_at, "org_id": doc.get("org_id"),
    }


def document_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": doc["_id"], "scope": doc["scope"], "scope_id": doc["scope_id"],
        "doc_type": doc["doc_type"], "title": doc["title"],
        "client_visible": bool(doc["client_visible"]), "media_id": doc["media_id"],
    }


def request_data(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": doc["_id"], "ref": doc["ref"], "org_id": doc["org_id"],
        "station_ids": list(doc["station_ids"]), "category": doc["category"],
        "priority": doc["priority"], "status": doc["status"], "title": doc["title"],
        "created_by": doc.get("created_by"),
        "assigned_staff_ids": list(doc.get("assigned_staff_ids", [])),
        "milestones": dict(doc.get("milestones") or {}),
        "reopen_count": doc.get("reopen_count"),
    }


def visit_data(visit: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    return {
        "visit_id": visit["_id"], "ref": visit["ref"], "request_id": request["_id"],
        "request_ref": request["ref"], "org_id": request["org_id"], "title": request.get("title"),
        "created_by": request.get("created_by"), "status": visit["status"],
        "planned_start": visit["planned_start"], "planned_end": visit["planned_end"],
        "staff_ids": list(visit["staff_ids"]), "lead_staff_id": visit["lead_staff_id"],
        "station_ids": [s["station_id"] for s in visit["stations"]],
        "station_owners": [
            {"station_id": s["station_id"], "owner_staff_id": s["owner_staff_id"]}
            for s in visit["stations"]
        ],
        "time_zone": next((s["time_zone"] for s in visit["stations"] if s.get("time_zone")), None),
    }


def visit_snapshot(visit: dict[str, Any]) -> dict[str, Any]:
    """A visit as the backfill sends it (TRD §8.6): the facts a read model keeps, with no notes."""
    return {
        "visit_id": visit["_id"], "ref": visit["ref"], "request_id": visit["request_id"],
        "org_id": visit["org_id"], "status": visit["status"],
        "planned_start": visit["planned_start"], "planned_end": visit["planned_end"],
        "staff_ids": list(visit["staff_ids"]), "lead_staff_id": visit["lead_staff_id"],
        "station_ids": [s["station_id"] for s in visit["stations"]],
        "started_at": visit.get("started_at"), "ended_at": visit.get("ended_at"),
        "additional_visit_required": visit.get("additional_visit_required"),
        "report_status": visit.get("report_status"),
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
        event_id: str | None = None,
    ) -> Envelope:
        envelope = Envelope(
            event_id=event_id or new_id(),
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

    async def qr_regenerated(
        self, station: dict[str, Any], session: AsyncClientSession
    ) -> Envelope:
        """QR-7. The tokens themselves stay out of the event and the audit record."""
        return await self.emit(
            ev.QrRegenerated(
                station_id=station["_id"], code=station["code"], org_id=station["owner_org_id"]
            ),
            type_="qr.regenerated", key=station["_id"], resource=("station", station["_id"]),
            aggregate_version=station["version"], org_id=station["owner_org_id"],
            session=session,
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

    async def calibration_voided(
        self, doc: dict[str, Any], unit: dict[str, Any] | None, session: AsyncClientSession, *,
        reason: str,
    ) -> Envelope:
        """A field calibration undone with its sensor action (TRD §3.2.3)."""
        return await self.emit(
            ev.CalibrationVoided(
                **calibration_data(doc, (unit or {}).get("calibration_due_at")), reason=reason
            ),
            type_="calibration.voided", key=str(doc.get("station_id") or doc["sensor_unit_id"]),
            resource=("calibration", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc.get("org_id"), session=session,
        )

    async def document(
        self, model: type[BaseModel], doc: dict[str, Any], session: AsyncClientSession, *,
        before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        """`document.uploaded` / `document.updated`, keyed by the station (or the model)."""
        type_ = "document.uploaded" if model is ev.DocumentUploaded else "document.updated"
        return await self.emit(
            model(**document_data(doc), **extra), type_=type_, key=doc["scope_id"],
            resource=("document", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc.get("org_id"), session=session,
            before=view(before, DOCUMENT_FIELDS), after=view(doc, DOCUMENT_FIELDS),
        )

    async def visibility(
        self, doc: dict[str, Any], visibility: str, session: AsyncClientSession
    ) -> Envelope:
        """Ask media to show a document's file to the owner organization, or hide it again
        (ADR-19). Sent in the transaction that attaches or changes the document, and
        versioned by the document, so media applies only the newest request."""
        return await self.emit(
            ev.MediaVisibilityRequested(
                media_ids=[doc["media_id"]], visibility=visibility,
                visibility_version=doc["version"],
            ),
            type_="media.visibility_requested", key=doc["scope_id"],
            resource=("document", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc.get("org_id"), session=session,
        )

    async def request(
        self, model: type[BaseModel], type_: str, doc: dict[str, Any],
        session: AsyncClientSession, *, before: dict[str, Any] | None = None,
        event_id: str | None = None, **extra: Any,
    ) -> Envelope:
        """A request event, keyed by the request (TRD §8.1) and versioned by it."""
        return await self.emit(
            model(**request_data(doc), **extra), type_=type_, key=doc["_id"],
            resource=("request", doc["_id"]), aggregate_version=doc["version"],
            org_id=doc["org_id"], session=session, event_id=event_id,
            before=view(before, REQUEST_FIELDS), after=view(doc, REQUEST_FIELDS),
        )

    async def request_status(
        self, doc: dict[str, Any], session: AsyncClientSession, *, from_status: str | None,
        event_id: str, reason: str | None = None,
    ) -> Envelope:
        """`request.status_changed`, sent next to the specific event for the same change."""
        return await self.request(
            ev.RequestStatusChanged, "request.status_changed", doc, session,
            event_id=event_id, from_status=from_status, to_status=doc["status"], reason=reason,
        )

    async def comment(
        self, model: type[BaseModel], type_: str, comment: dict[str, Any],
        request: dict[str, Any], session: AsyncClientSession, *,
        before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        """`comment.added` / `comment.updated`, keyed by the request (TRD §8.1) and versioned by
        the comment. The data names the comment, never its text."""
        return await self.emit(
            model(
                **request_data(request), comment_id=comment["_id"],
                author_id=comment["author_id"], author_name=comment["author_name"],
                author_role=comment["author_role"], internal=bool(comment["internal"]),
                attachment_count=len(comment["attachments"]), **extra,
            ),
            type_=type_, key=request["_id"], resource=("comment", comment["_id"]),
            aggregate_version=comment["version"], org_id=request["org_id"], session=session,
            before=view(before, COMMENT_FIELDS), after=view(comment, COMMENT_FIELDS),
        )

    async def attachments_visibility(
        self, owner_type: str, owner: dict[str, Any], request: dict[str, Any],
        media_ids: list[str], visibility: str, session: AsyncClientSession,
    ) -> Envelope:
        """Ask media to show a request's or comment's files to the organization, or keep them
        staff-only (ADR-19). Sent in the transaction that attaches them or changes who may see
        them, versioned by the owner so media applies only the newest request."""
        return await self.emit(
            ev.MediaVisibilityRequested(
                media_ids=media_ids, visibility=visibility, visibility_version=owner["version"],
            ),
            type_="media.visibility_requested", key=request["_id"],
            resource=(owner_type, owner["_id"]), aggregate_version=owner["version"],
            org_id=request["org_id"], session=session,
        )

    async def visit(
        self, model: type[BaseModel], type_: str, visit: dict[str, Any], request: dict[str, Any],
        session: AsyncClientSession, *, before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        """A visit event, keyed by its request (TRD §8.1) and versioned by the visit. The data
        holds the dates, people and stations a notification needs, never the visit's notes."""
        return await self.emit(
            model(**visit_data(visit, request), **extra), type_=type_, key=request["_id"],
            resource=("visit", visit["_id"]), aggregate_version=visit["version"],
            org_id=request["org_id"], session=session,
            before=view(before, VISIT_FIELDS), after=view(visit, VISIT_FIELDS),
        )

    async def element(
        self, model: type[BaseModel], type_: str, element: dict[str, Any], visit: dict[str, Any],
        request: dict[str, Any], session: AsyncClientSession, *,
        before: dict[str, Any] | None = None, **extra: Any,
    ) -> Envelope:
        """An element of a station's board (W11-35), keyed by the request and versioned by the
        element's `revision`. The event holds ids and flags; the audit block keeps the text."""
        return await self.emit(
            model(**visit_data(visit, request), **element_facts(element), **extra),
            type_=type_, key=request["_id"], resource=("visit_element", element["_id"]),
            aggregate_version=element["revision"], org_id=request["org_id"], session=session,
            before=view(before, ELEMENT_FIELDS), after=view(element, ELEMENT_FIELDS),
        )

    async def element_media(
        self, element: dict[str, Any], visit: dict[str, Any], request: dict[str, Any],
        session: AsyncClientSession, *, media_id: str, section: str, kind: str, change: str,
    ) -> Envelope:
        """A file on an element was added, captioned, hidden, shown or removed (W11-27)."""
        return await self.emit(
            ev.VisitMediaChanged(
                **visit_data(visit, request), station_id=element["station_id"],
                media_id=media_id, kind=kind, change=change, element_id=element["_id"],
                section=section,
            ),
            type_="visit.media_changed", key=request["_id"],
            resource=("visit_element", element["_id"]), aggregate_version=element["revision"],
            org_id=request["org_id"], session=session,
        )

    async def visit_visibility(
        self, media_ids: list[str], visibility: str, visit: dict[str, Any],
        session: AsyncClientSession, *, version: int,
    ) -> Envelope:
        """Ask media to show a visit's files to the client (when the visit ends, and for what is
        shared after), or keep them staff-only (unshared or hidden again). `version` comes from
        the visit's `visibility_seq`, so media applies only the newest request for each file
        (W11-13, W11-28)."""
        return await self.emit(
            ev.MediaVisibilityRequested(
                media_ids=media_ids, visibility=visibility, visibility_version=version,
            ),
            type_="media.visibility_requested", key=visit["request_id"],
            resource=("visit", visit["_id"]), aggregate_version=visit["version"],
            org_id=visit["org_id"], session=session,
        )

    async def media_deletion(
        self, media_ids: list[str], reason: str, visit: dict[str, Any], request: dict[str, Any],
        session: AsyncClientSession,
    ) -> Envelope:
        return await self.emit(
            ev.MediaDeletionRequested(media_ids=media_ids, reason=reason),
            type_="media.deletion_requested", key=request["_id"],
            resource=("visit", visit["_id"]), aggregate_version=visit["version"],
            org_id=request["org_id"], session=session,
        )

    async def config_version(
        self, version: dict[str, Any], station: dict[str, Any], session: AsyncClientSession
    ) -> Envelope:
        return await self.emit(
            ev.ConfigVersionCreated(
                station_id=version["station_id"], version=version["version"],
                file_count=len(version["files"]), visit_id=version.get("visit_id"),
            ),
            type_="config.version_created", key=version["station_id"],
            resource=("config_version", version["_id"]), aggregate_version=version["version"],
            org_id=station["owner_org_id"], session=session,
            after={"version": version["version"], "notes": version.get("notes"),
                   "files": [f["filename"] for f in version["files"]]},
        )


__all__ = [
    "Emitter", "calibration_data", "document_data", "ev", "model_data", "request_data",
    "station_data", "unit_data", "view",
]
