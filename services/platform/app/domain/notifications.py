"""Who is told what (PRD NOT-1, NOT-2, NOT-5, Appendix B; W9-10, W9-11). No I/O.

`plan()` turns one event into the notifications it makes and the live "something changed"
messages for open pages. It is one pure function so a test can walk every row of the matrix and
every role. Rules it keeps:

- The person who did it is never told about it.
- A notification holds no comment text, only who and where (so an internal comment, or one
  edited later, can't leak through a list).
- An internal comment reaches staff only, in the notification and in the live message.
- A visit's notes never travel: the events do not carry them, so no notification can.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

# The events this module turns into notifications or live updates.
NOTIFY_EVENTS = frozenset({
    "user.registered", "request.submitted", "request.approved", "request.denied",
    "request.assigned", "request.staff_changed", "request.released", "request.cancelled",
    "comment.added",
    "visit.scheduled", "visit.rescheduled", "visit.cancelled", "visit.ended",
    "visit.station_owner_changed",
})
VISIT_LIVE_EVENTS = frozenset({
    "visit.scheduled", "visit.rescheduled", "visit.cancelled", "visit.restored", "visit.started",
    "visit.ended", "visit.station_owner_changed", "visit.station_arrived",
    "visit.station_departed",
})
LIVE_EVENTS = frozenset({
    "request.updated", "request.status_changed", "request.assigned", "request.staff_changed",
    "request.released", "comment.added", "comment.updated",
}) | VISIT_LIVE_EVENTS


@dataclass(frozen=True)
class Audience:
    """Active people, from the user directory: who an event may be about."""

    admins: Sequence[str] = ()
    staff: Sequence[str] = ()  # technicians, admins and viewers: everyone who reads all requests
    org_clients: Sequence[str] = ()  # the client users of the event's organization


@dataclass(frozen=True)
class Draft:
    user_id: str
    type: str  # the preference key (NOT-4): request.assigned, comment.added, ...
    title: str
    body: str
    link: str
    entity_type: str = "request"
    entity_id: str = ""
    # Also worth an email for this person (PRD Appendix B); their choice decides at send time
    email: bool = False


@dataclass(frozen=True)
class Live:
    """`entity.updated` for pages that have this request or visit open (NOT-5)."""

    user_id: str
    entity_id: str
    status: str
    kind: str  # status | staff | comment | visit
    entity: str = "request"  # request | visit
    request_id: str = ""  # for a visit: the request it belongs to, so its page looks again


@dataclass(frozen=True)
class Plan:
    drafts: list[Draft] = field(default_factory=list)
    live: list[Live] = field(default_factory=list)


def _once(ids: Sequence[str], *, skip: str | None) -> list[str]:
    """Each person once, in order, without the person who acted."""
    return [i for i in dict.fromkeys(ids) if i != skip]


def _request_line(data: Mapping[str, Any]) -> str:
    return f"{data['ref']} · {data.get('title') or 'Maintenance request'}"


def _link(data: Mapping[str, Any]) -> str:
    return f"/requests/{data['request_id']}"


def plan(
    event_type: str, data: Mapping[str, Any], actor_id: str | None, actor_name: str | None,
    audience: Audience,
) -> Plan:
    drafts: list[Draft] = []
    who = actor_name or "Someone"

    def tell(ids: Sequence[str], type_: str, title: str, body: str, *, email: bool = False) -> None:
        for user_id in _once(ids, skip=actor_id):
            drafts.append(Draft(
                user_id=user_id, type=type_, title=title, body=body, link=_link(data),
                entity_id=data["request_id"], email=email,
            ))

    if event_type == "user.registered":
        for user_id in _once(audience.admins, skip=actor_id):
            drafts.append(Draft(
                user_id=user_id, type="account.registered", title="New registration",
                body=f"{data['name']} from {data['proposed_org_name']} is waiting for approval",
                link=f"/admin/registrations/{data['user_id']}",
                entity_type="user", entity_id=data["user_id"],
            ))
        return Plan(drafts=drafts)

    if event_type not in NOTIFY_EVENTS and event_type not in LIVE_EVENTS:
        return Plan()
    if event_type.startswith("visit."):
        return _plan_visit(event_type, data, actor_id, actor_name, audience)

    creator = [data["created_by"]] if data.get("created_by") else []
    assigned = list(data.get("assigned_staff_ids") or [])
    line = _request_line(data)

    match event_type:
        case "request.submitted":
            if not data.get("by_admin"):
                tell(audience.admins, "request.submitted", f"New request {data['ref']}",
                     data.get("title") or "", email=True)
        case "request.approved":
            tell(creator, "request.decided", "Request approved", line, email=True)
        case "request.denied":
            tell(creator, "request.decided", "Request denied", line, email=True)
        case "request.assigned":
            names = ", ".join(data.get("staff_names") or [])
            tell(data["staff_ids"], "request.assigned", "Assigned to you", line, email=True)
            tell(creator, "request.assigned", "A technician is on it", f"{names} · {line}")
            if data.get("claimed"):
                tell(audience.admins, "request.assigned", f"{who} claimed {data['ref']}",
                     data.get("title") or "")
        case "request.staff_changed":
            tell(data["added"], "request.assigned", "Assigned to you", line, email=True)
            tell(data["removed"], "request.staff_changed", "Removed from a request", line)
        case "request.released":
            tell(audience.admins, "request.released", f"{who} released {data['ref']}",
                 "It is back in the queue")
        case "request.cancelled":
            # The client and the people on the request may choose email; the admins hear in-app
            tell([*creator, *assigned], "request.cancelled", "Request cancelled", line,
                 email=True)
            others = [a for a in audience.admins if a not in {*creator, *assigned}]
            tell(others, "request.cancelled", "Request cancelled", line)
        case "comment.added":
            # Staff on the request hear about every comment; with nobody on it yet the admins do.
            staff = assigned or list(audience.admins)
            if data["internal"]:
                tell(staff, "comment.added", f"{data['author_name']} commented",
                     f"{line} · Internal comment")
            else:
                tell([*staff, *creator], "comment.added", f"{data['author_name']} commented",
                     line)
        case _:
            pass

    return Plan(drafts=drafts, live=_live(event_type, data, audience))


def _live(event_type: str, data: Mapping[str, Any], audience: Audience) -> list[Live]:
    if event_type not in LIVE_EVENTS:
        return []
    kind = {
        "request.updated": "status", "request.status_changed": "status",
        "request.assigned": "staff", "request.staff_changed": "staff",
        "request.released": "staff", "comment.added": "comment", "comment.updated": "comment",
    }[event_type]
    clients: Sequence[str] = audience.org_clients
    # A comment made internal is gone from a client's thread: tell them to look again. One that
    # was internal all along (and is only edited) is none of their business.
    if event_type == "comment.added" and data.get("internal"):
        clients = ()
    quiet_edit = data.get("internal") and not data.get("internal_changed")
    if event_type == "comment.updated" and quiet_edit:
        clients = ()
    ids = [*audience.staff, *clients]
    return [
        Live(user_id=i, entity_id=data["request_id"], status=data["status"], kind=kind)
        for i in dict.fromkeys(ids)
    ]


# --- Visits (W10; PRD VIS-11, Appendix B) ------------------------------------------------------


def when_text(data: Mapping[str, Any]) -> str:
    """`Thu 22 Oct, 08:00 EST`: the visit's start in the zone its dates are written in (the first
    station's), or UTC when the event names none."""
    start = data["planned_start"]
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    try:
        zone = ZoneInfo(data.get("time_zone") or "UTC")
    except (KeyError, ValueError):  # a zone the server doesn't know: say it in UTC
        zone = ZoneInfo("UTC")
    local = start.astimezone(zone) if start.tzinfo else start.replace(tzinfo=UTC).astimezone(zone)
    return f"{local:%a} {local.day} {local:%b}, {local:%H:%M} {local.tzname()}"


def _plan_visit(
    event_type: str, data: Mapping[str, Any], actor_id: str | None, actor_name: str | None,
    audience: Audience,
) -> Plan:
    """A visit event: who hears of it, and which open pages look again. The client who made the
    request and everyone attending hear of a plan, a new date or a cancellation (and may choose
    email for them); attending staff hear when it ends; the old and the new owner hear of a
    change. The person who did it is never told."""
    drafts: list[Draft] = []
    visit_id = data["visit_id"]
    line = f"{data['ref']} · {data.get('title') or 'Maintenance request'}"
    creator = [data["created_by"]] if data.get("created_by") else []
    attending = list(data.get("staff_ids") or [])

    def tell(ids: Sequence[str], type_: str, title: str, body: str, *, email: bool = False) -> None:
        for user_id in _once(ids, skip=actor_id):
            drafts.append(Draft(
                user_id=user_id, type=type_, title=title, body=body, link=f"/visits/{visit_id}",
                entity_type="visit", entity_id=visit_id, email=email,
            ))

    match event_type:
        case "visit.scheduled":
            tell([*attending, *creator], "visit.scheduled", "Visit planned",
                 f"{line} · {when_text(data)}", email=True)
        case "visit.rescheduled":
            tell([*attending, *creator], "visit.scheduled", "Visit rescheduled",
                 f"{line} · now {when_text(data)}", email=True)
        case "visit.cancelled":
            # A cancelled request already tells the client and the people on it
            if not data.get("by_request"):
                tell([*attending, *creator], "visit.cancelled", "Visit cancelled", line,
                     email=True)
        case "visit.ended":
            more = " · another visit needed" if data.get("additional_visit_required") else ""
            tell(attending, "visit.ended", "Visit ended", f"{data['ref']}{more}")
        case "visit.station_owner_changed":
            where = data.get("station_name") or data.get("station_code") or "a station"
            who = actor_name or "Someone"
            tell([data["to_staff_id"]], "visit.owner_changed", f"You now own {where}",
                 f"{data['ref']} · changed by {who}")
            tell([data["from_staff_id"]], "visit.owner_changed", f"You no longer own {where}",
                 f"{data['ref']} · changed by {who}")
        case _:
            pass

    live = [
        Live(user_id=i, entity_id=visit_id, status=data["status"], kind="visit", entity="visit",
             request_id=data["request_id"])
        for i in dict.fromkeys([*audience.staff, *audience.org_clients])
    ]
    return Plan(drafts=drafts, live=live)
