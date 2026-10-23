"""The field bundle (TRD §3.2.1, §7; PRD OFF-1; W13-9): everything a phone needs to carry out a
visit with no signal, in one document. Staff only; a client has no offline session (AUTH-12)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.api.requests.schemas import RequestDetail
from app.api.stations.doc_schemas import ConfigVersionOut, StationDocuments
from app.api.stations.schemas import CalibrationOut, StationDetail
from app.api.visits.element_schemas import ElementOut
from app.api.visits.schemas import VisitOut


class BundleStation(BaseModel):
    """One station of the visit: its record with the sensors installed, the calibration history,
    the latest configuration version, its documents and the visit's board for it."""

    station: StationDetail
    calibrations: list[CalibrationOut]
    config_version: ConfigVersionOut | None
    documents: StationDocuments
    board: list[ElementOut]
    can_add: bool  # whether the person may add to this board (as the board route says)


class BundleFile(BaseModel):
    """A file the phone can store as a blob. The phone asks for a ten-minute link when it
    downloads (`media_id` for a configuration file, `document_id` for a document) and never keeps
    the link (TRD §7.1). `required` files (the latest configuration version's) must be stored
    before the visit counts as ready."""

    kind: Literal["config", "document"]
    media_id: str
    document_id: str | None
    station_id: str  # the station whose page shows it (the first, for a model's document)
    name: str
    size: int
    sha256: str | None
    required: bool


class FieldBundle(BaseModel):
    bundle_version: int
    prepared_at: datetime
    visit: VisitOut
    request: RequestDetail
    stations: list[BundleStation]
    files: list[BundleFile]
