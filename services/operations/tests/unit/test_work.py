"""The work record's rules (PRD VIS-7, VIS-8; W11-1 to W11-4), no I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from mms_common.errors import Conflict, Forbidden, ValidationFailed

from app.domain.visits import work

NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)
ITEMS = [
    {"id": "i1", "label": "Mast", "help": None, "group": "Station", "template_id": "t1",
     "template_version": 3},
    {"id": "i2", "label": "Battery", "help": "Volts", "group": "Station", "template_id": "t1",
     "template_version": 3},
]
ACTION: dict[str, Any] = {
    "id": "a1", "action": "replace", "parameter": "AT", "sensor_model_id": None,
    "old_serial": "V-1", "new_serial": "V-2", "removal_reason": "faulty", "calibration": None,
    "note": None,
}


def visit(status: str = "started", **extra: Any) -> dict[str, Any]:
    return {"status": status, "locked": False, **extra}


def station(owner: str = "u1") -> dict[str, Any]:
    return {"station_id": "s1", "owner_staff_id": owner}


def record(**fields: Any) -> dict[str, Any]:
    return {"checklist": [], "sensor_actions": [], "config_versions": [], "parts_used": [],
            "issues_found": [], **fields}


# --- Who and when ------------------------------------------------------------------------------


@pytest.mark.req("VIS-7")
def test_the_owner_and_an_admin_save_while_the_visit_runs_or_has_ended():
    for status in ("started", "ended"):
        work.check_can_save(visit(status), station(), "u1", False)
        work.check_can_save(visit(status), station(), "boss", True)


@pytest.mark.req("VIS-7")
def test_anyone_else_is_refused_even_attending_staff():
    with pytest.raises(Forbidden) as e:
        work.check_can_save(visit(), station(), "u2", False)
    assert e.value.extra["code"] == "not_owner"


@pytest.mark.req("VIS-7")
@pytest.mark.parametrize(("status", "code"), [("planned", "not_started"),
                                              ("cancelled", "visit_cancelled")])
def test_a_visit_that_is_not_under_way_takes_no_record(status, code):
    with pytest.raises(Conflict) as e:
        work.check_can_save(visit(status), station(), "u1", False)
    assert e.value.extra["code"] == code


@pytest.mark.req("VIS-7")
def test_a_locked_visit_takes_no_record_not_even_from_an_admin():
    with pytest.raises(Conflict) as e:
        work.check_can_save(visit("ended", locked=True), station(), "boss", True)
    assert e.value.extra["code"] == "locked"


# --- The template copy (VIS-8) ------------------------------------------------------------------


@pytest.mark.req("VIS-8")
def test_a_new_record_copies_the_items_and_starts_every_check_unanswered():
    blank = work.blank(ITEMS, NOW)
    assert blank["version"] == 0 and blank["updated_by"] is None
    assert [i["id"] for i in blank["checklist_template"]["items"]] == ["i1", "i2"]
    assert blank["checklist_template"]["items"][0]["template_version"] == 3
    assert [(r["item_id"], r["result"], r["ad_hoc"]) for r in blank["checklist"]] == [
        ("i1", None, False), ("i2", None, False)]
    # a copy: changing it does not change the template the caller holds
    blank["checklist_template"]["items"][0]["label"] = "changed"
    assert ITEMS[0]["label"] == "Mast"


@pytest.mark.req("VIS-8")
def test_a_template_item_cannot_be_removed_and_comes_back_unanswered():
    current = work.blank(ITEMS, NOW)
    cleaned = work.clean_record(record(checklist=[{"item_id": "i2", "result": "ok",
                                                   "note": " fine "}]), current)
    rows = {r["item_id"]: r for r in cleaned["checklist"]}
    assert rows["i1"]["result"] is None and rows["i2"]["result"] == "ok"
    assert rows["i2"]["note"] == "fine"
    assert [r["item_id"] for r in cleaned["checklist"]] == ["i1", "i2"]  # the template's order


@pytest.mark.req("VIS-8")
def test_ad_hoc_items_are_kept_after_the_template_ones():
    current = work.blank(ITEMS, NOW)
    cleaned = work.clean_record(record(checklist=[
        {"item_id": "x1", "ad_hoc": True, "label": " Check the fence ", "result": "issue"},
    ]), current)
    assert [r["item_id"] for r in cleaned["checklist"]] == ["i1", "i2", "x1"]
    assert cleaned["checklist"][-1]["label"] == "Check the fence"
    assert cleaned["checklist"][-1]["ad_hoc"] is True


@pytest.mark.req("VIS-8")
@pytest.mark.parametrize(("rows", "code"), [
    ([{"item_id": "nope", "result": "ok"}], "unknown_item"),
    ([{"item_id": "i1"}, {"item_id": "i1"}], "duplicate_id"),
    ([{"item_id": "i1", "ad_hoc": True, "label": "x"}], "duplicate_id"),
    ([{"item_id": "x1", "ad_hoc": True, "label": "  "}], "required"),
    ([{"item_id": "x1", "ad_hoc": True, "label": "a"},
      {"item_id": "x1", "ad_hoc": True, "label": "b"}], "duplicate_id"),
    ([{"item_id": "i1", "result": "great"}], "bad_result"),
])
def test_the_checklist_is_checked(rows, code):
    with pytest.raises(ValidationFailed) as e:
        work.clean_record(record(checklist=rows), work.blank(ITEMS, NOW))
    assert e.value.extra["code"] == code


@pytest.mark.req("VIS-8")
def test_the_template_copy_and_the_servers_fields_are_never_taken_from_the_client():
    current = work.blank(ITEMS, NOW)
    cleaned = work.clean_record(record(
        checklist_template={"items": []}, version=99, updated_by="evil"), current)
    assert cleaned["checklist_template"] is current["checklist_template"]
    assert "version" not in cleaned and "updated_by" not in cleaned


# --- The rest of the record (VIS-7) -------------------------------------------------------------


@pytest.mark.req("VIS-7")
def test_sensor_actions_need_what_each_kind_needs():
    current = work.blank(ITEMS, NOW)
    ok = work.clean_record(record(sensor_actions=[dict(ACTION)]), current)
    assert ok["sensor_actions"][0]["new_serial"] == "V-2"
    cases = [
        ({"new_serial": None}, "serial_required"),
        ({"old_serial": None}, "serial_required"),
        ({"parameter": None}, "parameter_required"),
        ({"action": "calibrate", "calibration": None}, "calibration_required"),
        ({"calibration": {"result": "pass"}}, "unexpected_calibration"),
    ]
    for change, code in cases:
        with pytest.raises(ValidationFailed) as e:
            work.clean_record(record(sensor_actions=[{**ACTION, **change}]), current)
        assert e.value.extra["code"] == code, change
    clean = {**ACTION, "action": "clean", "parameter": None, "new_serial": None,
             "old_serial": "V-1"}
    assert work.clean_record(record(sensor_actions=[clean]), current)  # a note needs no parameter


@pytest.mark.req("VIS-7")
def test_entries_made_on_a_device_keep_their_ids_once_each():
    current = work.blank(ITEMS, NOW)
    for field, rows in (
        ("sensor_actions", [ACTION, ACTION]),
        ("parts_used", [{"id": "p", "description": "Fuse"}, {"id": "p", "description": "Fuse"}]),
        ("issues_found", [{"id": "q", "description": "Rust"}, {"id": "q", "description": "Rust"}]),
        ("config_versions", [{"id": "c", "files": ["f"]}, {"id": "c", "files": ["g"]}]),
    ):
        with pytest.raises(ValidationFailed) as e:
            work.clean_record(record(**{field: rows}), current)
        assert e.value.extra["code"] == "duplicate_id" and e.value.extra["field"] == field


@pytest.mark.req("VIS-7")
def test_lists_and_texts_are_bounded():
    current = work.blank(ITEMS, NOW)
    many = [{**ACTION, "id": f"a{n}"} for n in range(work.MAX_ACTIONS + 1)]
    with pytest.raises(ValidationFailed) as e:
        work.clean_record(record(sensor_actions=many), current)
    assert e.value.extra["code"] == "too_many"
    with pytest.raises(ValidationFailed) as e:
        work.clean_record(record(notes="x" * (work.MAX_NOTES + 1)), current)
    assert e.value.extra["code"] == "too_long"
    with pytest.raises(ValidationFailed):
        work.clean_record(record(parts_used=[{"id": "p", "description": "  "}]), current)
    with pytest.raises(ValidationFailed):
        work.clean_record(record(config_versions=[{"id": "c", "files": []}]), current)
    with pytest.raises(ValidationFailed):
        work.clean_record(record(config_versions=[{"id": "c", "files": ["f", "f"]}]), current)


@pytest.mark.req("VIS-7")
def test_conditions_and_the_download_period():
    current = work.blank(ITEMS, NOW)
    cleaned = work.clean_record(record(
        condition_on_arrival={"status": "degraded", "notes": " wet "},
        condition_on_departure={"status": None, "notes": None},
        data_downloaded={"done": True, "from": NOW, "to": NOW},
    ), current)
    assert cleaned["condition_on_arrival"] == {"status": "degraded", "notes": "wet"}
    assert cleaned["condition_on_departure"] is None  # nothing said
    assert cleaned["data_downloaded"]["done"] is True
    with pytest.raises(ValidationFailed) as e:
        work.clean_record(record(data_downloaded={
            "done": True, "from": NOW, "to": datetime(2026, 10, 1, tzinfo=UTC)}), current)
    assert e.value.extra["code"] == "bad_window"


# --- Saving (ADR-18: no merge) ------------------------------------------------------------------


@pytest.mark.req("VIS-7")
def test_a_save_stamps_the_next_version_the_person_and_the_device():
    current = work.blank(ITEMS, NOW)
    cleaned = work.clean_record(record(notes="Done"), current)
    stored = work.save(current, cleaned, 0, "u1", "phone-1", NOW)
    assert stored is not None
    assert (stored["version"], stored["updated_by"], stored["device_id"]) == (1, "u1", "phone-1")
    assert stored["updated_at"] == NOW and stored["notes"] == "Done"


@pytest.mark.req("VIS-7")
def test_the_same_content_again_changes_nothing_whatever_version_it_carries():
    current = work.blank(ITEMS, NOW)
    first = work.save(current, work.clean_record(record(notes="Done"), current), 0, "u1", None, NOW)
    assert first is not None
    again = work.clean_record(record(notes="Done"), first)
    assert work.save(first, again, 0, "u1", None, NOW) is None  # a retry after a lost answer
    assert work.save(first, again, 1, "u1", None, NOW) is None


@pytest.mark.req("VIS-7")
def test_a_save_from_an_older_version_is_a_conflict_and_nothing_is_merged():
    current = work.blank(ITEMS, NOW)
    first = work.save(current, work.clean_record(record(notes="One"), current), 0, "u1", None, NOW)
    assert first is not None
    other = work.clean_record(record(notes="Two"), first)
    with pytest.raises(Conflict) as e:
        work.save(first, other, 0, "u1", None, NOW)
    assert e.value.extra["code"] == "work_changed"
    assert work.save(first, other, 1, "u1", None, NOW)["version"] == 2  # type: ignore[index]


@pytest.mark.req("VIS-7")
def test_the_hash_ignores_the_servers_fields_and_notices_every_part():
    current = work.blank(ITEMS, NOW)
    base = work.clean_record(record(), current)
    assert work.content_hash({**base, "version": 7, "updated_by": "x"}) == work.content_hash(base)
    for change in (record(notes="n"), record(parts_used=[{"id": "p", "description": "Fuse"}]),
                   record(checklist=[{"item_id": "i1", "result": "ok"}])):
        assert work.content_hash(work.clean_record(change, current)) != work.content_hash(base)
