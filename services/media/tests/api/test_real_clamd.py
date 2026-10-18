"""The scan step against a real ClamAV daemon (PRD MED-3): it finds the EICAR test file, passes
clean files, and accepts streams past clamd's 25 MB default (documents go up to 50 MB).

The EICAR string goes straight to clamd here. Sending it through the store as well would work
in CI but not on a PC whose antivirus cuts connections that carry it; the job's handling of an
infected verdict is covered with a stand-in scanner (test_processing.py)."""

from __future__ import annotations

import pytest

from app.domain.media import ScanStatus
from app.repo.scanner import ClamdScanner

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


async def scan(scanner, chunks):
    session = await scanner.open()
    for chunk in chunks:
        await session.feed(chunk)
    return await session.finish()


@pytest.mark.req("MED-3")
async def test_clamd_finds_the_eicar_test_file_and_passes_clean_files(clamd):
    scanner = ClamdScanner(*clamd)
    assert await scanner.ping()
    clean = await scan(scanner, [b"%PDF-1.7 a clean file"])
    assert clean.status is ScanStatus.CLEAN
    infected = await scan(scanner, [EICAR])
    assert infected.infected and infected.signature == "Eicar-Test-Signature"
    big = await scan(scanner, [b"a" * (1024 * 1024)] * 55)  # past the 25 MB default
    assert big.status is ScanStatus.CLEAN
