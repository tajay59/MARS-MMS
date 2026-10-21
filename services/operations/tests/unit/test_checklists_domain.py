"""Checklist templates, W10 (PRD VIS-8; W10-11, W10-12): cleaning, the scope key, and which items a
station is given. Pure functions."""

from __future__ import annotations

import itertools
from typing import Any

import pytest
from mms_common.errors import ValidationFailed

from app.domain.checklists import starter, templates
from app.domain.checklists.templates import AddOn


def counter():
    n = itertools.count(1)
    return lambda: f"id-{next(n)}"


@pytest.mark.req("VIS-8")
def test_a_template_is_for_a_station_type_or_a_sensor_model_not_both_or_neither():
    assert templates.clean_scope(" AWS ", None) == ("AWS", None)
    assert templates.clean_scope(None, "m-1") == (None, "m-1")
    for pair in ((None, None), ("AWS", "m-1"), ("  ", None)):
        with pytest.raises(ValidationFailed) as caught:
            templates.clean_scope(*pair)
        assert caught.value.extra["code"] == "scope_required"
    with pytest.raises(ValidationFailed):
        templates.clean_scope("x" * 61, None)


@pytest.mark.req("VIS-8")
def test_the_scope_key_ignores_case_and_spaces_around_a_station_type():
    assert templates.scope_key("AWS", None) == templates.scope_key("  aws ", None)
    assert templates.scope_key("AWS", None) != templates.scope_key("Synoptic", None)
    assert templates.scope_key(None, "m-1") == "model:m-1"


@pytest.mark.req("VIS-8")
def test_items_are_cleaned_and_keep_their_ids():
    items = templates.clean_items(
        [{"id": "keep", "label": "  Mast  ", "help": " check guy wires "},
         {"label": "Battery", "help": "  "}],
        counter(),
    )
    assert items == [
        {"id": "keep", "label": "Mast", "help": "check guy wires"},
        {"id": "id-1", "label": "Battery", "help": None},
    ]


@pytest.mark.req("VIS-8")
@pytest.mark.parametrize(("items", "code"), [
    ([], "items_required"),
    ([{"label": "  "}], "required"),
    ([{"label": "x" * 201}], "too_long"),
    ([{"label": "ok", "help": "h" * 501}], "too_long"),
    ([{"id": "a", "label": "one"}, {"id": "a", "label": "two"}], "duplicate_item"),
    ([{"label": f"item {i}"} for i in range(61)], "too_many_items"),
])
def test_bad_items_are_refused(items, code):
    with pytest.raises(ValidationFailed) as caught:
        templates.clean_items(items, counter())
    assert caught.value.extra["code"] == code


@pytest.mark.req("VIS-8")
def test_a_name_is_required_and_short():
    assert templates.clean_name("  Site visit ") == "Site visit"
    for bad in ("  ", "n" * 101):
        with pytest.raises(ValidationFailed):
            templates.clean_name(bad)


def template(family: str, version: int, *labels: str) -> dict[str, Any]:
    return {"family_id": family, "version": version,
            "items": [{"id": f"{family}-{i}", "label": label, "help": None}
                      for i, label in enumerate(labels)]}


@pytest.mark.req("VIS-8")
def test_a_station_gets_its_type_template_then_an_add_on_for_each_installed_model():
    station = template("t1", 3, "Mast", "Battery")
    hmp = template("m1", 2, "Radiation shield clean")
    rain = template("m2", 1, "Funnel clear")
    out = templates.resolve(station, [
        AddOn("model-b", "Texas TB4", rain),
        AddOn("model-a", "Vaisala HMP155", hmp),
        AddOn("model-a", "Vaisala HMP155", hmp),  # two units of the same model: listed once
        AddOn("model-c", "Campbell CR1000", None),  # no add-on for this model
    ])
    assert [(i["group"], i["label"]) for i in out] == [
        ("Station", "Mast"), ("Station", "Battery"),
        ("Texas TB4", "Funnel clear"), ("Vaisala HMP155", "Radiation shield clean"),
    ]
    assert out[0]["template_id"] == "t1" and out[0]["template_version"] == 3
    assert out[3]["template_id"] == "m1" and out[3]["template_version"] == 2


@pytest.mark.req("VIS-8")
def test_a_station_with_no_template_gets_only_its_add_ons_and_none_at_all_is_empty():
    hmp = template("m1", 1, "Shield")
    assert [i["group"] for i in templates.resolve(None, [AddOn("a", "HMP", hmp)])] == ["HMP"]
    assert templates.resolve(None, []) == []


@pytest.mark.req("VIS-8")
def test_the_starter_checklist_is_valid_and_has_twelve_items():
    cleaned = templates.clean_items(
        [{"label": label, "help": help_} for label, help_ in starter.STARTER_ITEMS], counter()
    )
    assert len(cleaned) == 12
    templates.clean_name(starter.STARTER_NAME)
