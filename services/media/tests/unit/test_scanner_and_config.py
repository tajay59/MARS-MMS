"""The clamd client speaks INSTREAM correctly, and production cannot run without scanning."""

from __future__ import annotations

import asyncio
import struct

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain.media import ScanStatus
from app.repo.scanner import ClamdScanner, NoScanner, ScannerUnavailable


class FakeClamd:
    """Reads an INSTREAM request and answers like clamd."""

    def __init__(self, answer: bytes) -> None:
        self.answer = answer
        self.received = b""
        self.command = b""
        self.server: asyncio.Server | None = None

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.command = await reader.readuntil(b"\0")
        if self.command == b"zPING\0":
            writer.write(b"PONG\0")
        else:
            while True:
                (size,) = struct.unpack(">I", await reader.readexactly(4))
                if size == 0:
                    break
                self.received += await reader.readexactly(size)
            writer.write(self.answer)
        await writer.drain()
        writer.close()

    async def start(self) -> int:
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return int(self.server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()


async def scan(answer: bytes, data: bytes = b"hello world"):
    clamd = FakeClamd(answer)
    port = await clamd.start()
    try:
        session = await ClamdScanner("127.0.0.1", port).open()
        await session.feed(data[:5])
        await session.feed(data[5:])
        return await session.finish(), clamd
    finally:
        await clamd.stop()


async def test_a_clean_file_streams_through_and_is_clean():
    result, clamd = await scan(b"stream: OK\0")
    assert result.status is ScanStatus.CLEAN and not result.infected
    assert clamd.command == b"zINSTREAM\0"
    assert clamd.received == b"hello world"


async def test_a_found_signature_is_infected():
    result, _ = await scan(b"stream: Eicar-Test-Signature FOUND\0")
    assert result.infected and result.signature == "Eicar-Test-Signature"


async def test_clamd_errors_are_not_a_clean_bill():
    with pytest.raises(ScannerUnavailable):
        await scan(b"INSTREAM size limit exceeded. ERROR\0")


async def test_an_unreachable_clamd_is_unavailable():
    with pytest.raises(ScannerUnavailable):
        await ClamdScanner("127.0.0.1", 1, timeout_s=1).open()


async def test_ping():
    clamd = FakeClamd(b"")
    port = await clamd.start()
    try:
        assert await ClamdScanner("127.0.0.1", port).ping()
    finally:
        await clamd.stop()
    assert not await ClamdScanner("127.0.0.1", port, timeout_s=1).ping()


async def test_no_scanner_says_skipped():
    session = await NoScanner().open()
    await session.feed(b"x")
    result = await session.finish()
    assert result.status is ScanStatus.SKIPPED and not result.infected


@pytest.mark.req("MED-3")
def test_production_refuses_to_run_without_the_scan():
    with pytest.raises(ValidationError, match="not allowed in production"):
        Settings(environment="production", scan_mode="off")
    Settings(environment="staging", scan_mode="off")
    Settings(environment="production", scan_mode="clamd")
    with pytest.raises(ValidationError):
        Settings(scan_mode="maybe")
