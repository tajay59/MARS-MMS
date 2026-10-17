from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None
    name: str | None = None  # the audit record shows who acted without a lookup (AUD-2)
    roles: list[str] = Field(default_factory=list)
    ip: str | None = None
    user_agent: str | None = None
    device_id: str | None = None


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str


class Envelope(BaseModel):
    """The common wrapper every domain event carries (TRD §8.3)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    type: str
    version: int = 1
    occurred_at: datetime
    source: str
    key: str  # root aggregate ID: the Kafka message key (TRD §8.1)
    aggregate_version: int
    actor: Actor = Field(default_factory=Actor)
    org_id: str | None = None
    resource: Resource
    correlation_id: str | None = None
    audit: dict[str, Any] = Field(default_factory=lambda: {"before": None, "after": None})
    data: dict[str, Any] = Field(default_factory=dict)
