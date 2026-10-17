"""Event envelope and schema registry (TRD §8.3). Schemas are keyed by `(type, version)`."""

from mms_common.events.envelope import Actor, Envelope, Resource
from mms_common.events.registry import SCHEMAS, UnknownEvent, register, validate

__all__ = ["SCHEMAS", "Actor", "Envelope", "Resource", "UnknownEvent", "register", "validate"]
