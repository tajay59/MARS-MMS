"""The rules for what a stored file may be (PRD MED-3, MED-6; TRD §3.3, §10): pure functions."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain import media as m
from app.domain.media import Kind, Rejected, Status

MiB = 1024 * 1024


@given(size=st.integers(min_value=1, max_value=200 * MiB))
def test_parts_always_add_up_to_the_file(size):
    count = m.part_count(size)
    sizes = [m.expected_part_size(n, size) for n in range(1, count + 1)]
    assert sum(sizes) == size
    assert all(s == m.PART_SIZE for s in sizes[:-1])
    assert 0 < sizes[-1] <= m.PART_SIZE


@pytest.mark.parametrize(("size", "count"), [
    (1, 1), (8 * MiB, 1), (8 * MiB + 1, 2), (16 * MiB, 2), (200 * MiB, 25),
])
def test_part_counts(size, count):
    assert m.part_count(size) == count


def test_a_complete_set_of_parts_is_accepted():
    size = 17 * MiB
    stored = {1: 8 * MiB, 2: 8 * MiB, 3: 1 * MiB}
    assert m.check_parts(stored, size).ok


def test_missing_parts_are_the_clients_to_send():
    check = m.check_parts({1: 8 * MiB, 3: 1 * MiB}, 17 * MiB)
    assert check.missing == [2] and check.problem is None and not check.ok


@pytest.mark.parametrize("stored", [
    {1: 8 * MiB, 2: 8 * MiB, 3: 2 * MiB},  # last part bigger than announced
    {1: 7 * MiB, 2: 8 * MiB, 3: 2 * MiB},  # a short part in the middle
    {1: 8 * MiB, 2: 8 * MiB, 3: 1 * MiB, 4: 1},  # a part past the end
    {0: 5, 1: 8 * MiB, 2: 8 * MiB, 3: 1 * MiB},  # part zero
])
def test_parts_that_cannot_add_up_are_a_problem(stored):
    assert m.check_parts(stored, 17 * MiB).problem


def test_a_file_one_byte_over_the_limit_is_refused():
    m.check_size(Kind.PDF, 50 * MiB)
    with pytest.raises(Rejected) as e:
        m.check_size(Kind.PDF, 50 * MiB + 1)
    assert e.value.code == "too_large"
    with pytest.raises(Rejected):
        m.check_size(Kind.VIDEO, 200 * MiB + 1)
    with pytest.raises(Rejected):
        m.check_size(Kind.IMAGE, 25 * MiB + 1)
    with pytest.raises(Rejected) as e:
        m.check_size(Kind.PDF, 0)
    assert e.value.code == "empty_file"


@pytest.mark.parametrize(("name", "clean"), [
    ("../../etc/passwd", "passwd"), ("C:\\Users\\a\\manual.pdf", "manual.pdf"),
    ("  spaced name .pdf ", "spaced name .pdf"), ("a<b>:c.pdf", "abc.pdf"),
    ("x" * 300 + ".pdf", ("x" * 300 + ".pdf")[:200]),
])
def test_filenames_lose_paths_and_odd_characters(name, clean):
    assert m.clean_filename(name) == clean


@pytest.mark.parametrize("name", ["", "   ", "..", "///", "<>"])
def test_a_name_with_nothing_left_is_refused(name):
    with pytest.raises(Rejected):
        m.clean_filename(name)


@pytest.mark.parametrize(("kind", "name", "ok"), [
    (Kind.PDF, "a.PDF", True), (Kind.PDF, "a.docx", False), (Kind.PDF, "a", False),
    (Kind.DOCUMENT, "a.xlsx", True), (Kind.DOCUMENT, "a.exe", False),
    (Kind.DOCUMENT, "a.html", False), (Kind.DOCUMENT, "a.svg", False),
    (Kind.CONFIG, "logger.cr1000x", True), (Kind.CONFIG, "net.xml", True),
    (Kind.CONFIG, "noext", True), (Kind.CONFIG, "run.sh", False),
    (Kind.CONFIG, "x.html", False), (Kind.CONFIG, "x.JS", False),
])
def test_names_by_kind(kind, name, ok):
    if ok:
        m.check_name(kind, name)
    else:
        with pytest.raises(Rejected):
            m.check_name(kind, name)


def test_only_pdfs_and_plain_images_open_in_the_browser():
    assert m.disposition("a.pdf", inline=True).startswith("inline;")
    assert m.disposition("a.pdf", inline=False).startswith("attachment;")
    assert m.disposition("a.docx", inline=True).startswith("attachment;")
    assert m.disposition("a.html", inline=True).startswith("attachment;")
    assert "%C3%A9" in m.disposition("é.pdf", inline=True)  # UTF-8 filenames are encoded


def test_owner_references():
    owner = m.parse_owner("document:station:01900000-0000-7000-8000-0000000000a1")
    assert (owner.service, owner.type, owner.id) == (
        "operations", "document-station", "01900000-0000-7000-8000-0000000000a1"
    )
    assert m.parse_owner("config:abc").type == "config"
    for bad in ("", "x", "config:", "config:a b", "nope:abc", "config:../x", "a:b/c", ":a"):
        with pytest.raises(Rejected):
            m.parse_owner(bad)


def test_keys_are_made_from_ids_and_never_from_the_filename():
    owner = m.parse_owner("document:model:m1")
    assert m.object_key(None, owner, "mid", ".pdf") == "shared/document-model/m1/mid/original.pdf"
    assert m.object_key("org1", owner, "mid", "") == "org1/document-model/m1/mid/original"


@pytest.mark.parametrize(("kind", "name", "head", "ok"), [
    (Kind.PDF, "a.pdf", b"%PDF-1.4", True), (Kind.PDF, "a.pdf", b"<html>", False),
    (Kind.DOCUMENT, "a.docx", b"PK\x03\x04rest", True), (Kind.DOCUMENT, "a.docx", b"%PDF", False),
    (Kind.DOCUMENT, "a.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", True),
    (Kind.DOCUMENT, "a.png", b"\x89PNG\r\n\x1a\nrest", True),
    (Kind.DOCUMENT, "a.jpg", b"\xff\xd8\xff\xe0", True), (Kind.DOCUMENT, "a.jpg", b"GIF8", False),
    (Kind.DOCUMENT, "a.txt", b"plain text", True), (Kind.DOCUMENT, "a.txt", b"bin\x00ary", False),
    (Kind.DOCUMENT, "a.csv", b"a,b\n1,2", True),
    (Kind.CONFIG, "x.cr1", b"\x00\x01\x02", True),  # logger programs are binary
])
def test_content_must_match_the_name(kind, name, head, ok):
    assert (m.check_content(kind, name, head) is None) is ok


def test_the_status_machine_only_goes_forward():
    assert m.can_move(Status.PENDING, Status.UPLOADED)
    assert m.can_move(Status.UPLOADED, Status.PROCESSING)
    assert m.can_move(Status.PROCESSING, Status.READY)
    assert m.can_move(Status.PROCESSING, Status.UPLOADED)  # a stuck file is put back
    assert not m.can_move(Status.READY, Status.PENDING)
    assert not m.can_move(Status.PENDING, Status.READY)  # nothing is ready unchecked
    assert not m.can_move(Status.DELETED, Status.READY)
