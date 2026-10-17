"""An in-memory stand-in for the slice of Redis the revocation list and JWKS cache use, for
unit tests that don't need a real Redis. Expiry is not modelled."""

from __future__ import annotations

from typing import Any


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, name: str) -> str | None:
        return self.data.get(name)

    async def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        px: int | None = None,
    ) -> Any:
        if nx and name in self.data:
            return None
        self.data[name] = value
        return True

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.data.get(k) for k in keys]
