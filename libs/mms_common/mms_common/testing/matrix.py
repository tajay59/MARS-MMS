"""The authorization matrix (TP "Rule-enforcement tests": rules 3, 4, 5).

Each service keeps an expected-roles table, taken from the PRD §2.3 permission matrix, with
one entry per route. The test:

- fails if a route is missing from the table, or the table names a route that's gone, so a
  new route can't skip the matrix;
- fails if a mutating route admits `viewer`, unless it only touches the caller's own
  profile or session (`self_service`);
- calls every route as anonymous, as each seed user, as a revoked user and as a service,
  and checks 401 / 403 / allowed. A client calling a resource of another organization
  gets 404 (`cross_org`).

Path parameters get a fresh UUIDv7 and bodies are `{}`, so allowed callers get 404 or 422:
the matrix tests who may call, the API tests test what the call does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from mms_common.testing.seed import SEED_USERS, TestIssuer

PUBLIC = "public"  # no access token: login, register, refresh (cookie), password reset
ANY = "any"  # any signed-in user
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SAMPLE_ID = "01900000-0000-7000-8000-ffffffffffff"
_PARAM = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class Expect:
    roles: frozenset[str] | str = ANY
    self_service: bool = False
    services: frozenset[str] = frozenset()  # /internal/* routes: which services may call


def roles(*names: str, self_service: bool = False) -> Expect:
    return Expect(frozenset(names), self_service=self_service)


def service(*names: str) -> Expect:
    return Expect(PUBLIC, services=frozenset(names))


Route = tuple[str, str]  # (METHOD, path template)
Table = Mapping[Route, Expect]


def app_routes(app: FastAPI) -> set[Route]:
    """Every (method, path) under /api/ and /internal/, including included routers."""
    found: set[Route] = set()
    # FastAPI 0.14x includes routers lazily; iter_route_contexts flattens them with their
    # effective (prefixed) paths.
    for context in iter_route_contexts(app.routes):
        path, methods = context.path, context.methods
        if not isinstance(context.original_route, APIRoute) or not path:
            continue
        if path.startswith(("/api/", "/internal/")):
            found.update((method, path) for method in (methods or set()) - {"HEAD"})
    return found


def check_table(app: FastAPI, table: Table) -> list[str]:
    problems: list[str] = []
    actual = app_routes(app)
    for route in sorted(actual - table.keys()):
        problems.append(f"{route[0]} {route[1]}: not in the expected-roles table")
    for route in sorted(table.keys() - actual):
        problems.append(f"{route[0]} {route[1]}: in the table but not in the app")
    for (method, path), expect in table.items():
        allows_viewer = expect.roles == ANY or (
            isinstance(expect.roles, frozenset) and "viewer" in expect.roles
        )
        if method in MUTATING and allows_viewer and not expect.self_service:
            problems.append(f"{method} {path}: a mutating route admits viewer (rule 5)")
    return problems


@dataclass
class Matrix:
    client: httpx.AsyncClient
    issuer: TestIssuer
    table: Table
    revoked: Iterable[str] = ("disabled",)  # seed keys whose tokens the app must refuse
    cross_org: Mapping[Route, str] = field(default_factory=dict)  # route -> an ORG_A record

    async def run(self) -> list[str]:
        failures: list[str] = []
        for route, expect in sorted(self.table.items()):
            failures.extend(await self._check(route, expect))
        return failures

    async def _call(self, method: str, path: str, token: str | None) -> int:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        body: dict[str, object] | None = {} if method in MUTATING else None
        response = await self.client.request(method, path, headers=headers, json=body)
        return response.status_code

    async def _check(self, route: Route, expect: Expect) -> list[str]:
        method, path = route
        url = _PARAM.sub(SAMPLE_ID, path)
        tokens = self.issuer.tokens()
        failures: list[str] = []

        async def check(
            who: str, token: str | None, want: set[int] | None, target: str = url
        ) -> None:
            """`want=None` means allowed: anything but 401 and 403."""
            got = await self._call(method, target, token)
            if want is None and got in (401, 403):
                failures.append(f"{method} {path} as {who}: {got}, expected allowed")
            elif want is not None and got not in want:
                failures.append(f"{method} {path} as {who}: {got}, expected {sorted(want)}")

        if path.startswith("/internal/"):
            await check("anonymous", None, {401})
            await check("admin (user token)", tokens["admin"], {401})
            for name in ("auth", "operations", "media", "report", "platform"):
                # A service that may not call gets 401 (wrong credential type) or 403.
                want = None if name in expect.services else {401, 403}
                await check(f"service {name}", self.issuer.service_token(name), want)
            return failures

        if expect.roles == PUBLIC:
            return failures
        await check("anonymous", None, {401})
        await check("service token", self.issuer.service_token("operations"), {401})
        revoked = set(self.revoked)
        for key, user in SEED_USERS.items():
            if key in revoked:
                await check(key, tokens[key], {401})
                continue
            allowed = expect.roles == ANY or bool(set(user.roles) & set(expect.roles))
            await check(key, tokens[key], None if allowed else {403})
        record = self.cross_org.get(route)
        if record is not None:
            other = _PARAM.sub(record, path)
            await check("client_b1 (other org)", tokens["client_b1"], {404}, other)
        return failures
