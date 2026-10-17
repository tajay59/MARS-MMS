"""Schemas for the `data` of each event, keyed by `(type, version)`.

Consumer rule 1 (TRD §8.5): an unknown type or an invalid payload goes straight to the DLQ.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from mms_common.events.envelope import Envelope

SCHEMAS: dict[tuple[str, int], type[BaseModel]] = {}


class UnknownEvent(Exception):
    def __init__(self, type_: str, version: int) -> None:
        super().__init__(f"No schema registered for {type_} v{version}")
        self.type = type_
        self.version = version


def register[M: BaseModel](type_: str, version: int = 1) -> Callable[[type[M]], type[M]]:
    def wrap(model: type[M]) -> type[M]:
        key = (type_, version)
        if key in SCHEMAS:
            raise ValueError(f"Event schema {type_} v{version} is already registered")
        SCHEMAS[key] = model
        return model

    return wrap


def validate(envelope: Envelope) -> BaseModel:
    """Validate `envelope.data` against its registered schema. Raises `UnknownEvent` or
    `pydantic.ValidationError`."""
    model = SCHEMAS.get((envelope.type, envelope.version))
    if model is None:
        raise UnknownEvent(envelope.type, envelope.version)
    return model.model_validate(envelope.data)
