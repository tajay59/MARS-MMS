"""The audit trail (PRD AUD-1 to AUD-5, TRD §5.6, §12). No I/O here.

Each event becomes one record built from its envelope: actor, resource, organization and the
`audit.before/after` block. Records are chained: `hash = SHA-256(prev_hash ‖ canonical(record
without hash))`, so changing or removing any record breaks every hash after it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

from mms_common.events import Envelope
from mms_common.time import to_iso

GENESIS = "0" * 64

# Events that only drive notifications are not audited (TRD §12).
NOTIFICATION_ONLY = frozenset(
    {"calibration.due_digest", "request.review_reminder", "report.finalize_reminder",
     "visit.sync_conflict"}
)

# PRD AUD-1, action by action, with the event types that record it. A contract test checks
# that every type a built service produces has a schema and is audited (TRD §12).
AUD1: dict[str, tuple[str, ...]] = {
    "logins": ("auth.login_succeeded",),
    "failed logins": ("auth.login_failed",),
    "logouts": ("auth.logout",),
    "password resets": ("auth.password_reset_requested", "auth.password_reset"),
    "user, role and organization changes": (
        "user.invited", "user.created", "user.updated", "user.disabled", "user.purged",
        "org.created", "org.updated",
    ),
    "registration approvals and rejections": ("user.registered", "user.approved", "user.rejected"),
    "station, sensor and calibration changes": (
        "station.created", "station.updated", "sensor_model.created", "sensor_model.updated",
        "sensor_unit.created", "sensor_unit.updated",
        "sensor.installed", "sensor.removed", "sensor.application_reversed",
        "calibration.recorded", "calibration.voided",
    ),
    "document and configuration uploads": (
        "document.uploaded", "document.updated", "config.version_created",
    ),
    "request creation, edits, approval, denial, assignment, claim, cancellation": (
        "request.submitted", "request.updated", "request.approved", "request.denied",
        "request.assigned", "request.cancelled",
    ),
    "visit scheduling, start, end and overrides": (
        "visit.scheduled", "visit.rescheduled", "visit.cancelled", "visit.restored",
        "visit.started", "visit.ended", "visit.work_updated", "visit.station_owner_changed",
        "visit.station_arrived", "visit.station_departed",
    ),
    "media uploads and deletions": ("media.uploaded", "media.deleted"),
    "report finalization, signatures and reopening": (
        "report.signed", "report.finalized", "report.reopened",
    ),
    "client acceptance, rejection and auto-closure": ("request.closed", "request.reopened"),
    "QR regeneration": ("qr.regenerated",),
    "security": ("auth.token_reuse_detected",),
    "brand colour changes": ("branding.updated",),
}


def audited(event_type: str) -> bool:
    return event_type not in NOTIFICATION_ONLY


def _ms(value: datetime) -> datetime:
    """MongoDB keeps milliseconds; truncate first so the stored record hashes the same."""
    value = value.astimezone(UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def to_record(envelope: Envelope, received_at: datetime) -> dict[str, Any]:
    """The record before chaining: no `seq`, `prev_hash` or `hash` yet (AUD-2)."""
    audit = envelope.audit or {}
    return {
        "_id": envelope.event_id,
        "at": _ms(envelope.occurred_at),
        "received_at": _ms(received_at),
        "actor": envelope.actor.model_dump(mode="json"),
        "action": envelope.type,
        "event_version": envelope.version,
        "resource": envelope.resource.model_dump(mode="json"),
        "org_id": envelope.org_id,
        "before": audit.get("before"),
        "after": audit.get("after"),
        "metadata": envelope.data,
        "correlation_id": envelope.correlation_id,
        "source_service": envelope.source,
        "aggregate_version": envelope.aggregate_version,
    }


def _default(value: Any) -> str:
    if isinstance(value, datetime):
        # A client opened without tz_aware returns naive datetimes; they are UTC (rule 8).
        return to_iso(value if value.tzinfo else value.replace(tzinfo=UTC))
    raise TypeError(f"not JSON-serializable in an audit record: {type(value).__name__}")


def canonical(record: dict[str, Any]) -> bytes:
    """Sorted keys, no spaces, UTF-8, times as UTC ISO 8601 with milliseconds."""
    body = {k: v for k, v in record.items() if k != "hash"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=_default)
    return text.encode("utf-8")


def chain(record: dict[str, Any], seq: int, prev_hash: str) -> dict[str, Any]:
    linked = {**record, "seq": seq, "prev_hash": prev_hash}
    linked["hash"] = hashlib.sha256(prev_hash.encode() + canonical(linked)).hexdigest()
    return linked


def first_break(records: Iterable[dict[str, Any]], start_seq: int, prev_hash: str) -> int | None:
    """The `seq` of the first record that doesn't link, or None if the run is intact.
    `records` must be in `seq` order, starting at `start_seq`."""
    expected_seq, expected_prev = start_seq, prev_hash
    for record in records:
        if record.get("seq") != expected_seq or record.get("prev_hash") != expected_prev:
            return expected_seq
        recomputed = chain({k: v for k, v in record.items()
                            if k not in ("seq", "prev_hash", "hash")}, expected_seq, expected_prev)
        if recomputed["hash"] != record.get("hash"):
            return expected_seq
        expected_seq, expected_prev = expected_seq + 1, record["hash"]
    return None


def all_aud1_types() -> Iterator[str]:
    for types in AUD1.values():
        yield from types
