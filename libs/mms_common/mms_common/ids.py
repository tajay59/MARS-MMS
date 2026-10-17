"""UUIDv7 identifiers (CLAUDE.md rule 9, ADR-8).

Python 3.13 has no `uuid.uuid7`, so this builds one per RFC 9562: a 48-bit Unix
millisecond timestamp, version and variant bits, and 74 random bits. The clock and
the random source are injectable so tests get seeded, repeatable IDs.
"""

from __future__ import annotations

import random
import re
import secrets
import uuid
from collections.abc import Callable

from mms_common.time import Clock, SystemClock

# Matches the string form of a UUIDv7. Used to type `{id}` path parameters (TRD §3.0).
UUID7_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
_UUID7_RE = re.compile(UUID7_PATTERN)


def is_uuid7(value: str) -> bool:
    return _UUID7_RE.match(value) is not None


class IdGenerator:
    """Generates UUIDv7 strings, monotonic within one millisecond."""

    def __init__(
        self,
        clock: Clock | None = None,
        randbits: Callable[[int], int] | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._randbits = randbits or secrets.randbits
        self._last_ms = -1
        self._last_rand = 0

    def new(self) -> str:
        ms = int(self._clock.now().timestamp() * 1000)
        rand = self._randbits(74)
        if ms <= self._last_ms:
            # Same millisecond (or the clock stepped back): keep IDs increasing.
            ms = self._last_ms
            rand = self._last_rand + 1
            if rand >= 1 << 74:
                ms += 1
                rand = 0
        self._last_ms, self._last_rand = ms, rand
        rand_a = rand >> 62  # 12 bits
        rand_b = rand & ((1 << 62) - 1)  # 62 bits
        value = (ms & ((1 << 48) - 1)) << 80
        value |= 0x7 << 76
        value |= rand_a << 64
        value |= 0b10 << 62
        value |= rand_b
        return str(uuid.UUID(int=value))


def seeded(clock: Clock, seed: int = 0) -> IdGenerator:
    """A repeatable generator for tests (TP: seeded UUIDv7s)."""
    rng = random.Random(seed)  # noqa: S311 - test determinism, not security
    return IdGenerator(clock=clock, randbits=rng.getrandbits)


_default = IdGenerator()


def new_id() -> str:
    """A fresh UUIDv7 string from the system clock."""
    return _default.new()
