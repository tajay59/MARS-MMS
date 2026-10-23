"""The `report` consumer group on `mms.operations.events` (TRD §3.4 "Consumes", §8.5).

Updates the read model for dashboards and summary reports. Each handler writes one row through
the `aggregate_version` guard, so events and the backfill (`jobs/backfill.py`) can arrive in any
order (§8.6).
"""

from __future__ import annotations

from typing import Any

from mms_common.consumer import Handler
from mms_common.events import Envelope
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from app.domain import readmodel as rm
from app.repo import readmodel

TOPICS = ["mms.operations.events"]


def handlers(db: AsyncDatabase[dict[str, Any]]) -> dict[str, Handler]:
    def writer(collection: str, build: rm.Builder) -> Handler:
        async def handle(
            payload: BaseModel, envelope: Envelope, session: AsyncClientSession
        ) -> None:
            data = payload.model_dump()
            if collection == rm.CALIBRATIONS and not data.get("org_id"):
                data["org_id"] = envelope.org_id
            await readmodel.put(db, collection, build(data, envelope.aggregate_version), session)

        return handle

    async def calibration_voided(
        payload: BaseModel, envelope: Envelope, session: AsyncClientSession
    ) -> None:
        data = payload.model_dump()
        await readmodel.put(
            db, rm.CALIBRATIONS,
            rm.calibration_row({**data, "org_id": data.get("org_id") or envelope.org_id},
                               envelope.aggregate_version),
            session,
        )
        await readmodel.void_calibration(db, data["calibration_id"], session)

    out = {event: writer(collection, build) for event, (collection, build) in rm.BUILDERS.items()}
    out["calibration.voided"] = calibration_voided
    return out
