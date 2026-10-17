"""The breached-password check (AUTH-9, T1): k-anonymity, padding, and the fallback."""

import hashlib

import httpx
import pytest

from app.repo.breached import FileCheck, HibpCheck


def sha1(password: str) -> str:
    return hashlib.sha1(password.encode()).hexdigest().upper()  # noqa: S324 - HIBP uses SHA-1


def api(found: dict[str, int], seen: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.headers["Add-Padding"] == "true"
        prefix = request.url.path.rsplit("/", 1)[1]
        lines = [f"{h[5:]}:{n}" for h, n in found.items() if h.startswith(prefix)]
        lines.append("0000000000000000000000000000000000A:0")  # padding
        return httpx.Response(200, text="\r\n".join(lines))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_only_the_first_five_characters_leave_the_server():
    seen: list[str] = []
    check = HibpCheck("https://hibp.test/range/", 1, http=api({sha1("hunter2hunter2"): 12}, seen))
    assert await check.is_breached("hunter2hunter2")
    assert not await check.is_breached("a very unusual phrase")
    assert all(len(url.rsplit("/", 1)[1]) == 5 for url in seen)
    assert sha1("hunter2hunter2")[5:] not in "".join(seen)


async def test_padding_entries_do_not_count():
    seen: list[str] = []
    check = HibpCheck("https://hibp.test/range/", 1, http=api({}, seen))
    assert not await check.is_breached("anything at all")


@pytest.fixture
def local_list(tmp_path):
    path = tmp_path / "pwned.txt"
    path.write_text(f"{sha1('local breached 1')}:3\n\n", encoding="utf-8")
    return str(path)


async def test_falls_back_to_the_local_list_when_unreachable(local_list):
    def down(request):
        raise httpx.ConnectError("no route")

    http = httpx.AsyncClient(transport=httpx.MockTransport(down))
    check = HibpCheck("https://hibp.test/range/", 1, fallback=FileCheck(local_list), http=http)
    assert await check.is_breached("local breached 1")
    assert not await check.is_breached("not on the list")


async def test_unreachable_without_a_list_accepts_and_counts():
    def down(request):
        raise httpx.ConnectError("no route")

    http = httpx.AsyncClient(transport=httpx.MockTransport(down))
    assert not await HibpCheck("https://hibp.test/range/", 1, http=http).is_breached("x" * 12)
