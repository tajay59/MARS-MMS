"""The report service's read model (TRD 3.4 "Consumes", 5.4, 8.5, 8.6): rows from operations'
events, the version guard in both directions, and the backfill from its snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mms_common.consumer import Outcome
from mms_common.events import Envelope, Resource
from mms_common.ids import new_id

from app.events import consumer
from app.jobs import backfill

ORG, STATION, REQUEST, VISIT, CAL = "o-1", "s-1", "r-1", "v-1", "c-1"
T0 = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)


def event(
    type_: str, resource: str, version: int, data: dict[str, Any], key: str = REQUEST
) -> bytes:
    return Envelope(
        event_id=new_id(), type=type_, occurred_at=T0, source="operations", key=key,
        aggregate_version=version, resource=Resource(type=resource, id=key), org_id=ORG, data=data,
    ).model_dump_json().encode()


def station(version: int = 1, name: str = "Alpha") -> bytes:
    return event("station.created", "station", version, {
        "station_id": STATION, "code": "AL", "name": name, "org_id": ORG, "country": "JM",
        "status": "operational", "time_zone": "America/Jamaica", "via": "api",
    }, STATION)


def request(type_: str, version: int, status: str, **extra: Any) -> bytes:
    data = {
        "request_id": REQUEST, "ref": "MR-2026-0042", "org_id": ORG, "station_ids": [STATION],
        "category": "fault", "priority": "normal", "status": status, **extra,
    }
    if type_ == "request.status_changed":
        data.update(to_status=status)
    return event(type_, "request", version, data)


def visit(type_: str, version: int, status: str, **extra: Any) -> bytes:
    data = {
        "visit_id": VISIT, "ref": "VR-2026-0042-01", "request_id": REQUEST,
        "request_ref": "MR-2026-0042", "org_id": ORG, "status": status,
        "planned_start": T0.isoformat(), "planned_end": T0.isoformat(),
        "staff_ids": ["u-1"], "lead_staff_id": "u-1", "station_ids": [STATION],
        "station_owners": [{"station_id": STATION, "owner_staff_id": "u-1"}], **extra,
    }
    return event(type_, "visit", version, data)


async def processor(report):
    dead: list[str] = []

    async def dlq(raw: bytes, reason: str) -> None:
        dead.append(reason)

    p = consumer.processor(report.app.state.mongo, report.app.state.db, dlq, report.clock)
    return p, dead


async def test_station_events_make_and_update_a_row_and_old_ones_change_nothing(report):
    p, dead = await processor(report)
    created = station(2, "Alpha")
    assert await p.process(created) is Outcome.APPLIED
    assert await p.process(created) is Outcome.DUPLICATE
    assert await p.process(station(1, "Older name")) is Outcome.APPLIED
    row = await report.db["station_facts"].find_one({"_id": STATION})
    assert row["name"] == "Alpha" and row["aggregate_version"] == 2 and row["org_id"] == ORG
    assert not dead


async def test_a_request_keeps_its_status_and_milestones_as_events_arrive(report):
    p, _ = await processor(report)
    milestones = {"submitted_at": "2026-10-01T09:00:00Z"}
    await p.process(request("request.submitted", 1, "submitted", milestones=milestones))
    approved = {**milestones, "approved_at": "2026-10-02T09:00:00Z"}
    await p.process(request("request.approved", 2, "approved", milestones=approved))
    row = await report.db["request_facts"].find_one({"_id": REQUEST})
    assert row["status"] == "approved" and row["aggregate_version"] == 2
    assert row["submitted_at"] == datetime(2026, 10, 1, 9, 0)
    assert row["approved_at"] == datetime(2026, 10, 2, 9, 0)
    # The "next to" event of the same version changes nothing
    await p.process(request("request.status_changed", 2, "approved", milestones=approved))
    assert (await report.db["request_facts"].count_documents({})) == 1


async def test_a_visit_keeps_its_times_when_later_events_do_not_repeat_them(report):
    p, _ = await processor(report)
    await p.process(visit("visit.scheduled", 1, "planned"))
    await p.process(visit("visit.started", 2, "started", started_at=T0.isoformat()))
    await p.process(visit("visit.station_arrived", 3, "started", station_id=STATION))
    ended = visit(
        "visit.ended", 4, "ended", ended_at="2026-10-05T11:00:00Z", additional_visit_required=True,
    )
    await p.process(ended)
    row = await report.db["visit_facts"].find_one({"_id": VISIT})
    assert row["status"] == "ended" and row["aggregate_version"] == 4
    assert row["started_at"] == datetime(2026, 10, 5, 8, 0)
    assert row["ended_at"] == datetime(2026, 10, 5, 11, 0)
    assert row["additional_visit_required"] is True


async def test_board_events_do_not_touch_visit_facts(report):
    p, dead = await processor(report)
    await p.process(visit("visit.scheduled", 1, "planned"))
    added = visit(
        "visit.element_added", 1, "started", station_id=STATION, element_id="e-1", kind="note",
        shared=False, element_version=1,
    )
    assert await p.process(added) is Outcome.APPLIED
    row = await report.db["visit_facts"].find_one({"_id": VISIT})
    assert row["status"] == "planned"  # the element event has another aggregate's version
    assert not dead


async def test_a_calibration_is_stored_with_its_organization_and_can_be_voided(report):
    p, _ = await processor(report)
    data = {
        "calibration_id": CAL, "unit_id": "u-1", "station_id": STATION, "method": "lab",
        "at": "2026-09-01T00:00:00Z", "result": "pass", "due_at": "2027-09-01T00:00:00Z",
    }
    await p.process(event("calibration.recorded", "calibration", 1, data, CAL))
    row = await report.db["calibration_facts"].find_one({"_id": CAL})
    assert row["org_id"] == ORG and row["voided"] is False
    voided = event("calibration.voided", "calibration", 1, {**data, "reason": "undone"}, CAL)
    await p.process(voided)
    row = await report.db["calibration_facts"].find_one({"_id": CAL})
    assert row["voided"] is True


async def test_an_invalid_event_goes_to_the_dead_letter_queue(report):
    p, dead = await processor(report)
    assert await p.process(b"{nope") is Outcome.DEAD_LETTERED
    short = event("request.submitted", "request", 1, {"request_id": REQUEST})
    assert await p.process(short) is Outcome.DEAD_LETTERED
    assert len(dead) == 2


# --- the backfill ------------------------------------------------------------------------------


class Pages:
    """Operations' snapshot, a page at a time."""

    def __init__(self, items: dict[str, list[list[dict[str, Any]]]]) -> None:
        self.items = items
        self.asked: list[tuple[str, str | None]] = []

    async def snapshot(self, entity: str, after: str | None = None):
        self.asked.append((entity, after))
        pages = self.items.get(entity, [])
        index = 0 if after is None else int(after)
        more = str(index + 1) if index + 1 < len(pages) else None
        return [dict(i) for i in (pages[index] if pages else [])], more


def snapshot_source(name: str = "Alpha") -> Pages:
    station_item = {
        "station_id": STATION, "code": "AL", "name": name, "org_id": ORG, "country": "JM",
        "status": "operational", "aggregate_version": 3,
    }
    request_item = {
        "request_id": REQUEST, "ref": "MR-2026-0042", "org_id": ORG, "station_ids": [STATION],
        "category": "fault", "priority": "normal", "status": "closed", "title": "x",
        "assigned_staff_ids": ["u-1", "u-2"],
        "aggregate_version": 7, "milestones": {"closed_at": "2026-10-09T10:00:00Z"},
    }
    visit_item = {
        "visit_id": VISIT, "ref": "VR-2026-0042-01", "request_id": REQUEST, "org_id": ORG,
        "status": "ended", "planned_start": T0.isoformat(), "planned_end": T0.isoformat(),
        "staff_ids": ["u-1"], "lead_staff_id": "u-1", "station_ids": [STATION],
        "started_at": T0.isoformat(), "ended_at": "2026-10-05T11:00:00Z", "aggregate_version": 5,
    }
    cal = {
        "calibration_id": CAL, "unit_id": "u-1", "station_id": STATION, "method": "lab",
        "at": "2026-09-01T00:00:00Z", "result": "pass", "due_at": None, "org_id": ORG,
        "aggregate_version": 1,
    }
    unit = {
        "unit_id": "u-1", "serial": "SN-1", "model_id": "m-1", "status": "installed",
        "current_station_id": STATION, "calibration_due_at": "2027-09-01T00:00:00Z",
        "aggregate_version": 4,
    }
    model = {
        "model_id": "m-1", "kind": "sensor", "manufacturer": "Vaisala", "model": "HMP155",
        "parameters": ["AT", "RH"], "default_calibration_interval_days": 365, "aggregate_version": 2,
    }
    config = {
        "config_id": "cfg-1", "station_id": STATION, "version": 4, "file_count": 3,
        "visit_id": VISIT, "created_at": "2026-10-06T09:00:00Z", "aggregate_version": 1,
    }
    installation = {
        "installation_id": "ins-1", "unit_id": "u-1", "serial": "SN-1", "model_id": "m-1",
        "station_id": STATION, "parameter": "AT", "installed_at": "2026-09-01T00:00:00Z",
        "removed_at": None, "aggregate_version": 1,
    }
    return Pages({
        "stations": [[station_item]], "requests": [[request_item], []],
        "visits": [[visit_item]], "calibrations": [[cal]], "sensor_units": [[unit]],
        "sensor_models": [[model]], "config_versions": [[config]],
        "installations": [[installation]],
    })


async def test_the_backfill_pages_through_every_entity_and_a_repeat_writes_nothing(report):
    source = snapshot_source()
    first = await backfill.backfill(report.db, source)
    assert first == {
        "stations": (1, 1), "requests": (1, 1), "visits": (1, 1), "calibrations": (1, 1),
        "sensor_units": (1, 1), "sensor_models": (1, 1), "config_versions": (1, 1),
        "installations": (1, 1),
    }
    assert ("requests", "1") in source.asked  # it followed the cursor
    again = await backfill.backfill(report.db, snapshot_source())
    assert again == {
        "stations": (1, 0), "requests": (1, 0), "visits": (1, 0), "calibrations": (1, 0),
        "sensor_units": (1, 0), "sensor_models": (1, 0), "config_versions": (1, 0),
        "installations": (1, 1),  # an installation is merged field by field, so it is rewritten
    }
    row = await report.db["visit_facts"].find_one({"_id": VISIT})
    assert row["started_at"] == datetime(2026, 10, 5, 8, 0) and row["status"] == "ended"
    request_row = await report.db["request_facts"].find_one({"_id": REQUEST})
    assert request_row["closed_at"] == datetime(2026, 10, 9, 10, 0)
    assert request_row["assigned_ids"] == ["u-1", "u-2"]  # who is on it, for a technician's view
    unit = await report.db["unit_facts"].find_one({"_id": "u-1"})
    assert (unit["status"], unit["station_id"], unit["serial"]) == ("installed", STATION, "SN-1")
    model = await report.db["model_facts"].find_one({"_id": "m-1"})
    assert (model["manufacturer"], model["interval_days"]) == ("Vaisala", 365)
    config = await report.db["config_facts"].find_one({"_id": "cfg-1"})
    assert (config["number"], config["file_count"], config["visit_id"]) == (4, 3, VISIT)
    assert config["created_at"] == datetime(2026, 10, 6, 9, 0)
    installed = await report.db["installation_facts"].find_one({"_id": "ins-1"})
    assert installed["installed_at"] == datetime(2026, 9, 1) and "removed_at" not in installed
    assert unit["due_at"] == datetime(2027, 9, 1, 0, 0)


async def test_an_event_newer_than_the_snapshot_wins_in_either_order(report):
    p, _ = await processor(report)
    await p.process(station(9, "Renamed by an event"))
    await backfill.backfill(report.db, snapshot_source("Name at the snapshot"))  # version 3
    row = await report.db["station_facts"].find_one({"_id": STATION})
    assert row["name"] == "Renamed by an event"
    # And the other way: the snapshot first, then an older event
    await report.db["station_facts"].delete_many({})
    await backfill.backfill(report.db, snapshot_source("Name at the snapshot"))
    await p.process(station(2, "Older event"))
    row = await report.db["station_facts"].find_one({"_id": STATION})
    assert row["name"] == "Name at the snapshot"


async def test_the_read_model_has_its_indexes(report):
    names = {i["name"] async for i in await report.db["request_facts"].list_indexes()}
    assert "org_id_1_status_1" in names


async def test_unit_events_make_and_update_a_row_and_old_ones_change_nothing(report):
    p, dead = await processor(report)

    def unit(type_: str, version: int, status: str, due: str | None, **extra: Any) -> bytes:
        return event(type_, "sensor_unit", version, {
            "unit_id": "u-1", "serial": "SN-1", "model_id": "m-1", "status": status,
            "current_station_id": STATION, "calibration_due_at": due, **extra,
        }, "u-1")

    assert await p.process(unit("sensor_unit.created", 1, "in_stock", None)) is Outcome.APPLIED
    assert await p.process(unit("sensor_unit.updated", 3, "installed", "2027-01-01T00:00:00Z",
                                changed_fields=["status"])) is Outcome.APPLIED
    await p.process(unit("sensor_unit.updated", 2, "in_repair", None, changed_fields=["status"]))
    row = await report.db["unit_facts"].find_one({"_id": "u-1"})
    assert (row["status"], row["aggregate_version"]) == ("installed", 3)
    assert row["due_at"] == datetime(2027, 1, 1, 0, 0)
    assert not dead


async def test_models_configuration_versions_and_installations_come_from_events(report):
    p, dead = await processor(report)
    model = event("sensor_model.created", "sensor_model", 1, {
        "model_id": "m-9", "kind": "sensor", "manufacturer": "Vaisala", "model": "HMP155",
        "parameters": ["AT"], "default_calibration_interval_days": 365}, "m-9")
    assert await p.process(model) is Outcome.APPLIED
    assert (await report.db["model_facts"].find_one({"_id": "m-9"}))["model"] == "HMP155"

    # a configuration version takes its id from the resource and its time from the envelope
    config = Envelope(
        event_id=new_id(), type="config.version_created", occurred_at=T0, source="operations",
        key=STATION, aggregate_version=4, resource=Resource(type="config_version", id="cfg-9"),
        org_id=ORG, data={"station_id": STATION, "version": 4, "file_count": 2, "visit_id": None},
    ).model_dump_json().encode()
    assert await p.process(config) is Outcome.APPLIED
    row = await report.db["config_facts"].find_one({"_id": "cfg-9"})
    assert (row["number"], row["file_count"], row["created_at"]) == (4, 2, datetime(2026, 10, 5, 8, 0))

    # an installation is written by two events, in either order
    def sensor(type_: str, at: str) -> bytes:
        return event(type_, "sensor_unit", 1, {
            "installation_id": "ins-9", "unit_id": "u-9", "serial": "SN-9", "model_id": "m-9",
            "station_id": STATION, "parameter": "AT", "at": at, "unit_status": "installed"},
            "u-9")

    assert await p.process(sensor("sensor.removed", "2026-10-04T00:00:00Z")) is Outcome.APPLIED
    assert await p.process(sensor("sensor.installed", "2026-09-01T00:00:00Z")) is Outcome.APPLIED
    got = await report.db["installation_facts"].find_one({"_id": "ins-9"})
    assert got["installed_at"] == datetime(2026, 9, 1) and got["removed_at"] == datetime(2026, 10, 4)
    assert (got["serial"], got["model_id"], got["parameter"]) == ("SN-9", "m-9", "AT")
    assert not dead
