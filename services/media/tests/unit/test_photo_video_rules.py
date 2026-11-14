"""What a photo or a video must look like before it is processed (PRD MED-3, MED-6; TRD §15):
names and first bytes. No I/O."""

from __future__ import annotations

import pytest

from app.domain import media as rules
from app.domain.media import Kind, Rejected

JPEG = bytes.fromhex("ffd8ffe000104a464946")
PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 8
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00"
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00"
MOOV_FIRST = b"\x00\x00\x00\x08moov" + b"\x00" * 8
WEBM = bytes.fromhex("1a45dfa3") + b"\x01\x00\x00\x00"


@pytest.mark.req("MED-3")
@pytest.mark.parametrize(("name", "head"), [
    ("IMG_1.JPG", JPEG), ("a.jpeg", JPEG), ("a.png", PNG), ("a.webp", WEBP),
    ("IMG_0001.HEIC", HEIC), ("a.heif", HEIC),
])
def test_photos_are_known_by_their_first_bytes(name, head):
    assert rules.check_name(Kind.IMAGE, name)
    assert rules.check_content(Kind.IMAGE, name, head) is None


@pytest.mark.req("MED-3")
@pytest.mark.parametrize(("name", "head"), [
    ("VID_1.mp4", MP4), ("a.m4v", MP4), ("IMG_9.MOV", MOV), ("a.mov", MOOV_FIRST),
    ("a.webm", WEBM),
])
def test_videos_are_known_by_their_first_bytes(name, head):
    assert rules.check_name(Kind.VIDEO, name)
    assert rules.check_content(Kind.VIDEO, name, head) is None


@pytest.mark.req("MED-3")
@pytest.mark.parametrize(("kind", "name", "head"), [
    (Kind.IMAGE, "a.jpg", PNG),  # a png called jpg
    (Kind.IMAGE, "a.png", JPEG),
    (Kind.IMAGE, "a.jpg", b"%PDF-1.7 not a photo"),
    (Kind.IMAGE, "a.heic", JPEG),  # a jpeg called heic
    (Kind.IMAGE, "a.webp", PNG),
    (Kind.VIDEO, "a.mp4", JPEG),
    (Kind.VIDEO, "a.mp4", b"this is a text file"),
    (Kind.VIDEO, "a.webm", MP4),
    (Kind.IMAGE, "a.jpg", b""),
])
def test_a_file_that_is_not_what_its_name_says_is_refused(kind, name, head):
    assert rules.check_content(kind, name, head) is not None


@pytest.mark.req("MED-3")
@pytest.mark.parametrize(("kind", "name"), [
    (Kind.IMAGE, "a.gif"), (Kind.IMAGE, "a.svg"), (Kind.IMAGE, "a.exe"), (Kind.IMAGE, "a"),
    (Kind.IMAGE, "a.mp4"), (Kind.VIDEO, "a.jpg"), (Kind.VIDEO, "a.avi"), (Kind.VIDEO, "clip"),
])
def test_other_types_are_refused_by_name(kind, name):
    with pytest.raises(Rejected) as e:
        rules.check_name(kind, name)
    assert e.value.code == "bad_type"


@pytest.mark.req("MED-6")
def test_the_limits_are_25_mb_a_photo_and_200_mb_a_video():
    rules.check_size(Kind.IMAGE, 25 * rules.MiB)
    rules.check_size(Kind.VIDEO, 200 * rules.MiB)
    for kind, size in ((Kind.IMAGE, 25 * rules.MiB + 1), (Kind.VIDEO, 200 * rules.MiB + 1)):
        with pytest.raises(Rejected) as e:
            rules.check_size(kind, size)
        assert e.value.code == "too_large"


def test_content_types_cover_what_the_copies_are_served_as():
    assert rules.content_type("a.heic") == "image/heic"
    assert rules.content_type("a.mov") == "video/quicktime"
    assert rules.content_type("a.xyz") == "application/octet-stream"
