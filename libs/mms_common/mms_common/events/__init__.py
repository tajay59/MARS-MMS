"""Event envelope and schema registry (TRD §8.3). Schemas are keyed by `(type, version)`.

Importing this package registers every producer's schemas, so any consumer can validate
any event (TRD §8.5 rule 1).
"""

from mms_common.events import auth as auth
from mms_common.events import operations as operations
from mms_common.events.envelope import Actor, Envelope, Resource
from mms_common.events.registry import SCHEMAS, UnknownEvent, register, validate

__all__ = [
    "SCHEMAS",
    "Actor",
    "Envelope",
    "Resource",
    "UnknownEvent",
    "auth",
    "operations",
    "register",
    "validate",
]
