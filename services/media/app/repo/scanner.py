"""Virus scanning with ClamAV's clamd over its INSTREAM protocol (PRD MED-3, TRD §3.3).

A scan session takes the file's chunks as they are read, so the same pass that hashes the
file also scans it. `NoScanner` is for hosts too small to run ClamAV (staging, TRD T8): it
says `skipped`, and the service refuses to start with it in production.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from typing import Protocol

from app.domain.media import ScanStatus

CLAMD_CHUNK = 1024 * 1024


class ScannerUnavailable(Exception):
    """clamd could not be reached or answered with an error. The file stays unscanned and the
    job tries again; a file is never released unscanned."""


@dataclass(frozen=True)
class ScanResult:
    status: ScanStatus | None  # None means infected
    signature: str | None = None

    @property
    def infected(self) -> bool:
        return self.status is None


class ScanSession(Protocol):
    async def feed(self, chunk: bytes) -> None: ...

    async def finish(self) -> ScanResult: ...


class Scanner(Protocol):
    async def open(self) -> ScanSession: ...


# --- clamd ---------------------------------------------------------------------------------


class _ClamdSession:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader, self._writer = reader, writer

    async def feed(self, chunk: bytes) -> None:
        try:
            for i in range(0, len(chunk), CLAMD_CHUNK):
                part = chunk[i : i + CLAMD_CHUNK]
                self._writer.write(struct.pack(">I", len(part)) + part)
            await self._writer.drain()
        except OSError as e:
            await self._close()
            raise ScannerUnavailable(str(e)) from e

    async def finish(self) -> ScanResult:
        try:
            self._writer.write(struct.pack(">I", 0))
            await self._writer.drain()
            reply = (await self._reader.readuntil(b"\0")).rstrip(b"\0").decode("utf-8", "replace")
        except (OSError, asyncio.IncompleteReadError) as e:
            raise ScannerUnavailable(str(e)) from e
        finally:
            await self._close()
        # "stream: OK", "stream: <signature> FOUND" or "<reason> ERROR"
        text = reply.removeprefix("stream:").strip()
        if text == "OK":
            return ScanResult(ScanStatus.CLEAN)
        if text.endswith("FOUND"):
            return ScanResult(None, text.removesuffix("FOUND").strip())
        raise ScannerUnavailable(text or "empty reply")

    async def _close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except OSError:
            pass


class ClamdScanner:
    def __init__(self, host: str, port: int, timeout_s: float = 10.0) -> None:
        self._host, self._port, self._timeout = host, port, timeout_s

    async def open(self) -> ScanSession:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
            writer.write(b"zINSTREAM\0")
            await writer.drain()
        except (OSError, TimeoutError) as e:
            raise ScannerUnavailable(str(e)) from e
        return _ClamdSession(reader, writer)

    async def ping(self) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
            writer.write(b"zPING\0")
            await writer.drain()
            reply = await asyncio.wait_for(reader.readuntil(b"\0"), self._timeout)
            writer.close()
        except (OSError, TimeoutError, asyncio.IncompleteReadError):
            return False
        return reply.startswith(b"PONG")


# --- off -----------------------------------------------------------------------------------


class _SkippedSession:
    async def feed(self, chunk: bytes) -> None:
        return None

    async def finish(self) -> ScanResult:
        return ScanResult(ScanStatus.SKIPPED)


class NoScanner:
    async def open(self) -> ScanSession:
        return _SkippedSession()
