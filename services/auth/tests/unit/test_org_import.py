"""The organization import from the existing system's `org` export (decision W5-8; TRD T4).
The documents here are made up; the repo is public."""

import json

import pytest

from app.domain import org_import


def doc(n: int, **extra):
    base = {
        "_id": {"$oid": f"00000000000000000000000{n}"},
        "id": f"ENT{n:032x}",
        "name": f"ORG{n}",
        "country": "Somewhere",
        "code": "bb",
        "organization": f"Organization {n} Meteorological Service",
        # The real export carries MQTT credentials: they must never be read or copied
        "web": {"username": "not-a-real-user", "password": "not-a-real-password"},
        "device": {"username": "not-a-real-user", "password": "not-a-real-password"},
        "websubtopic": "/station/data/org/#",
    }
    return {**base, **extra}


@pytest.mark.req("ORG-1")
def test_reads_a_json_array_and_json_lines():
    docs = [doc(1), doc(2)]
    as_array = json.dumps(docs).encode()
    as_lines = "\n".join(json.dumps(d) for d in docs).encode()
    assert org_import.read_export(as_array) == docs
    assert org_import.read_export(b"\xef\xbb\xbf" + as_lines) == docs
    assert org_import.read_export(b"  ") == []


@pytest.mark.parametrize("content", [b"{not json", b'"text"', b"[1, 2]"])
def test_rejects_what_is_not_an_export(content):
    with pytest.raises(org_import.ExportError):
        org_import.read_export(content)


@pytest.mark.req("ORG-1")
def test_maps_full_name_short_name_country_and_external_id():
    result = org_import.plan([doc(1)], existing_external_ids=set(), existing_name_keys=set())
    assert result.errors == [] and result.skipped == []
    [row] = result.create
    assert (row.name, row.short_name, row.country, row.external_id) == (
        "Organization 1 Meteorological Service", "ORG1", "BB", f"ENT{1:032x}",
    )
    # Only these fields exist on a row: nothing else from the document can leak through
    assert set(vars(row)) == {"number", "name", "short_name", "country", "external_id"}
    assert "not-a-real" not in repr(result)


def test_short_name_alone_becomes_the_name():
    result = org_import.plan([doc(1, organization="")], existing_external_ids=set(),
                             existing_name_keys=set())
    assert (result.create[0].name, result.create[0].short_name) == ("ORG1", None)


def test_skips_what_exists_and_reports_bad_or_repeated_documents():
    docs = [
        doc(1),
        doc(2),
        doc(3, code="Saint Somewhere"),
        doc(4, id=""),
        doc(5, id=f"ENT{2:032x}", organization="Another name"),
        doc(6, organization="  organization 6 METEOROLOGICAL service "),
    ]
    result = org_import.plan(
        docs,
        existing_external_ids={f"ENT{1:032x}"},
        existing_name_keys={"organization 6 meteorological service"},
    )
    assert [p.number for p in result.skipped] == [1, 6]
    assert [p.number for p in result.errors] == [3, 4, 5]
    assert "two-letter country code" in result.errors[0].message
    assert "also in document 2" in result.errors[2].message
    assert [r.number for r in result.create] == [2]
