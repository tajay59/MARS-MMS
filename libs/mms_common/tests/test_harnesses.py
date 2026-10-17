"""The authorization matrix and client leak harnesses catch what they are meant to catch."""

from typing import Annotated

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI

from mms_common.auth import (
    Authenticator,
    User,
    install_auth,
    require_roles,
    require_staff,
    revocation,
)
from mms_common.testing.leak import find_leaks
from mms_common.testing.matrix import ANY, PUBLIC, Expect, Matrix, check_table, roles
from mms_common.testing.memory import MemoryStore
from mms_common.testing.seed import SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from mms_common.web import install


def build(post_roles=("admin",)):
    clock = ManualClock()
    issuer = TestIssuer(clock)
    store = MemoryStore()
    app = FastAPI()
    install(app)
    install_auth(app, Authenticator(issuer.keys, clock, store))

    @app.get("/api/v1/widgets/{id}")
    async def read(id: str, user: Annotated[User, Depends(require_staff())]):
        return {"id": id}

    # In an included router: FastAPI includes these lazily, and the matrix must still see them.
    router = APIRouter(prefix="/api/v1/widgets")

    @router.post("")
    async def create(user: Annotated[User, Depends(require_roles(*post_roles))]):
        return {}

    app.include_router(router)

    @app.post("/api/v1/hello")
    async def hello():
        return {}

    return app, issuer, store, clock


TABLE = {
    ("GET", "/api/v1/widgets/{id}"): roles("technician", "admin", "viewer"),
    ("POST", "/api/v1/widgets"): roles("admin"),
    ("POST", "/api/v1/hello"): Expect(PUBLIC),
}


def test_table_must_cover_every_route():
    app, *_ = build()
    partial = dict(TABLE)
    del partial[("POST", "/api/v1/widgets")]
    partial[("GET", "/api/v1/gone")] = Expect(ANY)
    problems = check_table(app, partial)
    assert any("not in the expected-roles table" in p for p in problems)
    assert any("not in the app" in p for p in problems)


def test_mutating_route_admitting_viewer_fails_the_table():
    app, *_ = build()
    bad = dict(TABLE)
    bad[("POST", "/api/v1/widgets")] = roles("admin", "viewer")
    assert any("admits viewer" in p for p in check_table(app, bad))
    bad[("POST", "/api/v1/widgets")] = roles("viewer", self_service=True)
    assert not check_table(app, bad)


async def test_matrix_passes_when_code_matches_the_table():
    app, issuer, store, clock = build()
    await revocation.revoke_user(store, SEED_USERS["disabled"].id, clock.now())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert check_table(app, TABLE) == []
        assert await Matrix(c, issuer, TABLE).run() == []


async def test_matrix_catches_code_that_lets_a_technician_in():
    app, issuer, store, clock = build(post_roles=("admin", "technician"))
    await revocation.revoke_user(store, SEED_USERS["disabled"].id, clock.now())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        failures = await Matrix(c, issuer, TABLE).run()
    assert any("as tech1: 4" in f or "as tech1: 2" in f for f in failures), failures


@pytest.mark.parametrize(
    ("body", "leaks"),
    [
        ({"id": "me", "email": "me@x"}, []),
        ({"items": [{"id": "staff1", "name": "T", "email": "t@x"}]}, ["$.items[0].email"]),
        ({"staff": [{"id": "s", "name": "T", "phone": "1"}]}, ["$.staff[0].phone"]),
        ({"id": "me", "password_hash": "x"}, ["$.password_hash"]),
        ({"comments": [{"id": "c", "internal": True}]}, ["$.comments[0] (internal)"]),
    ],
)
def test_leak_finder(body, leaks):
    assert find_leaks(body, own_ids=frozenset({"me"})) == leaks
