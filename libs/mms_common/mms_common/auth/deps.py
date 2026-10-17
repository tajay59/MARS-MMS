"""FastAPI dependencies: who is calling, and may they (TRD §6.3).

    @router.post("/api/v1/requests/{id}/approve")
    async def approve(id: str, user: Annotated[User, Depends(require_roles("admin"))]): ...

Every mutating route uses `require_roles(...)` without `viewer` (rule 5). The dependencies
raise before FastAPI reports body errors, so an unauthorised caller gets 401/403, never 422.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mms_common.auth import revocation
from mms_common.auth.principal import ServicePrincipal, User
from mms_common.auth.roles import STAFF, USER_ROLES
from mms_common.auth.tokens import ACCESS_AUDIENCE, SERVICE_AUDIENCE, KeySource, verify
from mms_common.errors import Forbidden, Unauthenticated
from mms_common.events.envelope import Actor
from mms_common.time import Clock

_bearer = HTTPBearer(auto_error=False, description="Access token from POST /api/v1/auth/login")
_SAFE_DEVICE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DEVICE_HEADER = "X-Device-ID"


class Authenticator:
    def __init__(self, keys: KeySource, clock: Clock, revocations: revocation.Store | None) -> None:
        self.keys = keys
        self.clock = clock
        self.revocations = revocations

    async def user(self, token: str) -> User:
        claims = await verify(token, self.keys, clock=self.clock, audience=ACCESS_AUDIENCE)
        roles = claims.get("roles")
        if not isinstance(roles, list) or not roles or not set(roles) <= USER_ROLES:
            raise Unauthenticated("Invalid token")
        org_id = claims.get("org_id")
        if self.revocations is not None and await revocation.is_revoked(
            self.revocations, user_id=claims["sub"], org_id=org_id, issued_at=claims["iat"]
        ):
            raise Unauthenticated("Session ended", reason="session_revoked")
        return User(
            id=str(claims["sub"]),
            roles=frozenset(roles),
            org_id=org_id if isinstance(org_id, str) else None,
            name=str(claims.get("name") or ""),
            token_id=str(claims["jti"]),
        )

    async def service(self, token: str) -> ServicePrincipal:
        claims = await verify(token, self.keys, clock=self.clock, audience=SERVICE_AUDIENCE)
        if claims.get("roles") != ["service"]:
            raise Unauthenticated("Invalid token")
        return ServicePrincipal(name=str(claims["sub"]))


def install_auth(app: FastAPI, authenticator: Authenticator) -> None:
    app.state.authenticator = authenticator


def _authenticator(request: Request) -> Authenticator:
    found: Authenticator | None = getattr(request.app.state, "authenticator", None)
    if found is None:
        raise RuntimeError("mms_common.auth.install_auth was not called for this app")
    return found


Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def current_user(request: Request, credentials: Credentials) -> User:
    if credentials is None:
        raise Unauthenticated()
    user = await _authenticator(request).user(credentials.credentials)
    request.state.user = user
    return user


RoleDependency = Callable[..., Awaitable[User]]


def require_roles(*roles: str) -> RoleDependency:
    """The caller must hold at least one of `roles`. `require_roles()` means any user."""
    wanted = frozenset(roles)
    unknown = wanted - USER_ROLES
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")

    async def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if wanted and not user.roles & wanted:
            raise Forbidden()
        return user

    dependency.allowed_roles = wanted or USER_ROLES  # type: ignore[attr-defined]
    return dependency


def require_staff() -> RoleDependency:
    """Read access for every staff role, viewers included. Never use it on a mutating route."""
    return require_roles(*STAFF)


def require_service(*names: str) -> Callable[..., Awaitable[ServicePrincipal]]:
    """`/internal/*` routes: a service token from one of `names` (TRD §6.4)."""
    allowed = frozenset(names)

    async def dependency(request: Request, credentials: Credentials) -> ServicePrincipal:
        if credentials is None:
            raise Unauthenticated()
        service = await _authenticator(request).service(credentials.credentials)
        if allowed and service.name not in allowed:
            raise Forbidden()
        return service

    return dependency


def client_ip(request: Request) -> str | None:
    """The browser's address. Services are reachable only through Nginx, which sets X-Real-IP."""
    real = request.headers.get("X-Real-IP")
    if real:
        return real[:64]
    return request.client.host if request.client else None


def actor_for(request: Request, user: User | None = None, **override: Any) -> Actor:
    """The `actor` block of an event raised by this request (TRD §8.3, AUD-2)."""
    device = request.headers.get(DEVICE_HEADER, "")
    fields: dict[str, Any] = {
        "user_id": user.id if user else None,
        "name": user.name if user else None,
        "roles": sorted(user.roles) if user else [],
        "ip": client_ip(request),
        "user_agent": (request.headers.get("User-Agent") or "")[:256] or None,
        "device_id": device if _SAFE_DEVICE.match(device) else None,
    }
    fields.update(override)
    return Actor(**fields)
