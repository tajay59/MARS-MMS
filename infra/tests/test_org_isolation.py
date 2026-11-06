"""A client of one organization against another organization's records, through the gateway
(ASVS V4 access control; rules 3, 4 and 6; ADR-16; W20 slice 5).

The authorization matrix in each service proves this one service at a time, with the code under
test. This is the same claim from outside, through Nginx, on a running stack with real tokens:

- every record of organization B that a client of organization A could name answers exactly as an
  id that does not exist does (same status, same error), so a client cannot tell "not yours" from
  "not there" (ADR-16: 404, never 403, and no existence oracle in the body)
- no list a client of A reads names anything of B's
- the same goes for actions: the answer for B's record is the answer for a missing one, never 2xx

    docker compose -f compose.yml -f compose.dev.yml up -d
    ../.venv/Scripts/python -m pytest tests/test_org_isolation.py -q

Skipped when the stack is not running.
"""

from __future__ import annotations

import json
import time

import pytest
from test_stack import (  # noqa: F401 - fixtures by name
    _compose,
    _login,
    _uuid7,
    api,
    mongo_up,
    seeded,
    web,
)

ORG_A = "01900000-0000-7000-8000-00000000a000"
ORG_B = "01900000-0000-7000-8000-00000000b000"


def _comparable(response) -> tuple[int, str]:
    """What a caller learns from an answer: the status and the error's type and code. The request
    id, the instance path and the timestamp are expected to differ and are left out."""
    try:
        body = response.json()
    except ValueError:
        return response.status_code, ""
    if isinstance(body, dict):
        return response.status_code, json.dumps(
            {k: body.get(k) for k in ("type", "title", "code", "status") if k in body}, sort_keys=True
        )
    return response.status_code, ""


@pytest.fixture(scope="module")
def world(web, seeded, mongo_up):  # noqa: F811
    """Tokens for staff and both clients, and one of B's stations, requests and sensor units."""
    for _ in range(30):  # operations copies the organizations from auth
        r = _compose("exec", "-T", "operations", "python", "-m", "app.cli", "seed")
        if r.returncode == 0 and "Errors" not in r.stdout:
            break
        time.sleep(2)
    assert r.returncode == 0, r.stdout + r.stderr
    admin = _login(web, "admin@example.org", seeded)
    client_a = _login(web, "client.a1@example.org", seeded)
    client_b = _login(web, "client.b1@example.org", seeded)

    stations = api(web, "GET", "/api/v1/stations", admin, params={"q": "-00"}).json()["items"]
    b_station = next(s for s in stations if s["owner_org_id"] == ORG_B)
    a_station = next(s for s in stations if s["owner_org_id"] == ORG_A)

    # B raises a request and comments on it
    request_id = _uuid7()
    created = api(web, "POST", "/api/v1/requests", client_b, json={
        "id": request_id, "title": "Isolation check", "description": "Made by the isolation test.",
        "category": "fault", "priority": "normal", "station_ids": [b_station["id"]],
    })
    assert created.status_code in (200, 201), created.text
    comment = api(web, "POST", f"/api/v1/requests/{request_id}/comments", client_b,
                  json={"id": _uuid7(), "body": "A note from B."})
    assert comment.status_code in (200, 201), comment.text

    units = api(web, "GET", "/api/v1/sensor-units", admin, params={"station_id": b_station["id"]})
    unit_ids = [u["id"] for u in units.json().get("items", [])] if units.status_code == 200 else []

    detail = api(web, "GET", f"/api/v1/stations/{b_station['id']}", admin).json()
    return {
        "web": web, "admin": admin, "a": client_a, "b": client_b,
        "b_station": b_station["id"], "a_station": a_station["id"],
        "b_request": request_id, "b_comment": comment.json().get("id"),
        "b_unit": unit_ids[0] if unit_ids else None,
        "b_qr": detail.get("qr_token"),
    }


# (method, path with {station} {request} {comment} {unit} {qr}, body). Every one is a route a
# client can reach; for a staff-only route the role check answers first, the same for any id.
ROUTES = [
    ("GET", "/api/v1/stations/{station}", None),
    ("PATCH", "/api/v1/stations/{station}", {}),
    ("GET", "/api/v1/stations/{station}/installations", None),
    ("GET", "/api/v1/stations/{station}/documents", None),
    ("GET", "/api/v1/stations/{station}/config-versions", None),
    ("POST", "/api/v1/stations/{station}/qr/regenerate", {}),
    ("GET", "/api/v1/qr/{qr}", None),
    ("GET", "/api/v1/requests/{request}", None),
    ("PATCH", "/api/v1/requests/{request}", {}),
    ("GET", "/api/v1/requests/{request}/comments", None),
    ("POST", "/api/v1/requests/{request}/comments", {"body": "I should not be able to say this."}),
    ("POST", "/api/v1/requests/{request}/cancel", {}),
    ("POST", "/api/v1/requests/{request}/accept", {}),
    ("POST", "/api/v1/requests/{request}/reject", {}),
    ("GET", "/api/v1/sensor-units/{unit}", None),
    ("POST", "/api/v1/sensor-units/{unit}/remove", {}),
]


def _fill(path: str, ids: dict[str, str | None], missing: bool) -> str | None:
    out = path
    for key in ("station", "request", "comment", "unit", "qr"):
        marker = "{" + key + "}"
        if marker in out:
            value = ids[key]
            if value is None:
                return None
            out = out.replace(marker, _uuid7() if missing else value)
    return out


@pytest.mark.parametrize(("method", "path", "body"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_another_organizations_record_answers_like_one_that_does_not_exist(world, method, path, body):
    ids = {"station": world["b_station"], "request": world["b_request"],
           "comment": world["b_comment"], "unit": world["b_unit"], "qr": world["b_qr"]}
    theirs = _fill(path, ids, missing=False)
    if theirs is None:
        pytest.skip("the demo data has no such record")
    ours = _fill(path, ids, missing=True)
    kwargs = {"json": body} if body is not None else {}
    asked = api(world["web"], method, theirs, world["a"], **kwargs)
    control = api(world["web"], method, ours, world["a"], **kwargs)
    assert asked.status_code not in (200, 201, 202, 204), (method, path, asked.status_code, asked.text[:200])
    assert _comparable(asked) == _comparable(control), (method, path, asked.text[:200], control.text[:200])


def test_a_client_can_still_use_its_own_records(world):
    """The control: the same routes work for the owner, so the 404s above are about scope."""
    site = world["web"]
    assert api(site, "GET", f"/api/v1/stations/{world['a_station']}", world["a"]).status_code == 200
    assert api(site, "GET", f"/api/v1/requests/{world['b_request']}", world["b"]).status_code == 200
    comments = api(site, "GET", f"/api/v1/requests/{world['b_request']}/comments", world["b"])
    assert comments.status_code == 200 and comments.json()["items"]


LISTS = ["/api/v1/stations", "/api/v1/requests", "/api/v1/sensor-units", "/api/v1/calibrations/due",
         "/api/v1/visits", "/api/v1/documents", "/api/v1/client-reports"]


@pytest.mark.parametrize("path", LISTS)
def test_no_list_a_client_reads_names_another_organization(world, path):
    r = api(world["web"], "GET", path, world["a"], params={"limit": 200})
    if r.status_code in (400, 403, 404, 422):
        return  # the route is not for clients, or needs a filter: nothing is listed
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    text = r.text
    for secret in (ORG_B, world["b_station"], world["b_request"]):
        assert secret not in text, (path, secret)


def test_the_gateway_does_not_publish_metrics_or_internal_routes(world):
    site = world["web"]
    for path in ("/metrics", "/internal/snapshot/stations", "/api/v1/../internal/snapshot/stations"):
        assert api(site, "GET", path, world["admin"]).status_code == 404, path
