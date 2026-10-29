"""JWT tests at each service (TP "Security"): wrong key, `alg: none`, `alg` confusion, expired
token, a service token used as an access token, a token for a disabled user. Plus roles,
scoping and the JWKS cache."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta
from typing import Annotated

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI

from mms_common.auth import (
    Authenticator,
    ServicePrincipal,
    User,
    install_auth,
    require_roles,
    require_service,
    require_staff,
    revocation,
    scoped,
    valid_role_set,
)
from mms_common.auth.jwks import JwksKeys
from mms_common.auth.tokens import (
    ACCESS_AUDIENCE,
    SigningKey,
    StaticKeys,
    issue_access,
    verify,
)
from mms_common.errors import Unauthenticated
from mms_common.testing.memory import MemoryStore
from mms_common.testing.seed import ORG_A, SEED_USERS, TestIssuer
from mms_common.time import ManualClock
from mms_common.web import install


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def issuer(clock):
    return TestIssuer(clock)


@pytest.fixture
def store():
    return MemoryStore()


def make_app(issuer, clock, store):
    app = FastAPI()
    install(app)
    install_auth(app, Authenticator(issuer.keys, clock, store))

    @app.get("/api/v1/things")
    async def read(user: Annotated[User, Depends(require_staff())]):
        return {"id": user.id}

    @app.post("/api/v1/things")
    async def write(user: Annotated[User, Depends(require_roles("technician", "admin"))]):
        return {"ok": True}

    @app.get("/api/v1/me")
    async def me(user: Annotated[User, Depends(require_roles())]):
        return {"roles": sorted(user.roles)}

    @app.get("/internal/thing")
    async def internal(svc: Annotated[ServicePrincipal, Depends(require_service("platform"))]):
        return {"service": svc.name}

    return app


async def call(app, method, path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, headers=headers)


async def status(app, method, path, token=None):
    return (await call(app, method, path, token)).status_code


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


@pytest.mark.req("NFR-6")
async def test_valid_token_is_accepted(issuer, clock, store):
    r = await call(make_app(issuer, clock, store), "GET", "/api/v1/things", issuer.token("tech1"))
    assert r.status_code == 200
    assert r.json() == {"id": SEED_USERS["tech1"].id}


@pytest.mark.req("NFR-6")
async def test_no_token_is_401_problem_json(issuer, clock, store):
    r = await call(make_app(issuer, clock, store), "GET", "/api/v1/things")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.req("NFR-6")
async def test_token_signed_by_another_key_is_refused(issuer, clock, store):
    other = TestIssuer(clock)
    other.signing.kid = issuer.signing.kid  # same kid, different key
    token = jwt.encode(
        {"sub": "x", "aud": ACCESS_AUDIENCE, "iss": "aws-mms-auth", "iat": 1, "exp": 2**40,
         "jti": "j", "roles": ["admin"]},
        other.signing.private_key, algorithm="EdDSA", headers={"kid": issuer.signing.kid},
    )
    r = await call(make_app(issuer, clock, store), "GET", "/api/v1/things", token)
    assert r.status_code == 401


@pytest.mark.req("NFR-6")
async def test_alg_none_is_refused(issuer, clock, store):
    claims = {"sub": SEED_USERS["admin"].id, "aud": ACCESS_AUDIENCE, "iss": "aws-mms-auth",
              "iat": int(clock.now().timestamp()), "exp": 2**40, "jti": "j", "roles": ["admin"]}
    token = f"{b64({'alg': 'none', 'kid': issuer.signing.kid})}.{b64(claims)}."
    r = await call(make_app(issuer, clock, store), "GET", "/api/v1/things", token)
    assert r.status_code == 401


@pytest.mark.req("NFR-6")
async def test_alg_confusion_hs256_with_the_public_key_is_refused(issuer, clock, store):
    claims = {"sub": SEED_USERS["admin"].id, "aud": ACCESS_AUDIENCE, "iss": "aws-mms-auth",
              "iat": int(clock.now().timestamp()), "exp": 2**40, "jti": "j", "roles": ["admin"]}
    signing_input = f"{b64({'alg': 'HS256', 'kid': issuer.signing.kid})}.{b64(claims)}"
    secret = issuer.signing.jwk["x"].encode()
    sig = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"
    r = await call(make_app(issuer, clock, store), "GET", "/api/v1/things", token)
    assert r.status_code == 401


@pytest.mark.req("NFR-6")
async def test_expired_token_is_refused(issuer, clock, store):
    token = issuer.token("tech1")
    clock.advance(minutes=16)
    r = await call(make_app(issuer, clock, store), "GET", "/api/v1/things", token)
    assert r.status_code == 401
    assert r.json()["reason"] == "token_expired"


@pytest.mark.req("NFR-6")
async def test_service_token_is_not_an_access_token_and_back(issuer, clock, store):
    app = make_app(issuer, clock, store)
    assert await status(app, "GET", "/api/v1/me", issuer.service_token("platform")) == 401
    assert await status(app, "GET", "/internal/thing", issuer.token("admin")) == 401
    assert await status(app, "GET", "/internal/thing", issuer.service_token("platform")) == 200
    assert await status(app, "GET", "/internal/thing", issuer.service_token("media")) == 403


@pytest.mark.req("AUTH-11")
async def test_token_of_a_disabled_user_is_refused(issuer, clock, store):
    app = make_app(issuer, clock, store)
    token = issuer.token("tech1")
    await revocation.revoke_user(store, SEED_USERS["tech1"].id, clock.now())
    r = await call(app, "GET", "/api/v1/things", token)
    assert r.status_code == 401
    assert r.json()["reason"] == "session_revoked"
    clock.advance(seconds=2)  # a token issued after re-enabling works
    assert await status(app, "GET", "/api/v1/things", issuer.token("tech1")) == 200


@pytest.mark.req("AUTH-11")
async def test_one_key_ends_every_token_issued_before_it(issuer, clock, store):
    """After a restore from backup (W20-9) nobody keeps an old session."""
    app = make_app(issuer, clock, store)
    old = [issuer.token(who) for who in ("tech1", "admin", "client_a1")]
    await revocation.revoke_all(store, clock.now())
    for token in old:
        assert (await call(app, "GET", "/api/v1/me", token)).status_code == 401
    clock.advance(seconds=2)
    assert await status(app, "GET", "/api/v1/me", issuer.token("tech1")) == 200


@pytest.mark.req("ORG-4")
async def test_tokens_of_a_deactivated_org_are_refused(issuer, clock, store):
    app = make_app(issuer, clock, store)
    token = issuer.token("client_a1")
    await revocation.revoke_org(store, ORG_A, clock.now())
    assert (await call(app, "GET", "/api/v1/me", token)).status_code == 401
    assert await status(app, "GET", "/api/v1/me", issuer.token("client_b1")) == 200


async def test_roles(issuer, clock, store):
    app = make_app(issuer, clock, store)
    assert await status(app, "GET", "/api/v1/things", issuer.token("viewer")) == 200
    assert await status(app, "POST", "/api/v1/things", issuer.token("viewer")) == 403
    assert await status(app, "GET", "/api/v1/things", issuer.token("client_a1")) == 403
    assert await status(app, "POST", "/api/v1/things", issuer.token("tech_admin")) == 200
    assert await status(app, "GET", "/api/v1/me", issuer.token("client_a1")) == 200


def test_unknown_role_name_fails_at_import():
    with pytest.raises(ValueError):
        require_roles("superuser")


@pytest.mark.parametrize(
    ("held", "ok"),
    [(["client"], True), (["technician", "admin"], True), (["viewer"], True),
     (["client", "admin"], False), ([], False), (["root"], False)],
)
def test_role_sets(held, ok):
    assert valid_role_set(held) is ok


def test_scoped_forces_the_clients_org():
    client = User("u", frozenset({"client"}), ORG_A, "C", "j")
    staff = User("s", frozenset({"technician"}), None, "T", "j")
    assert scoped(client, {"x": 1}) == {"org_id": ORG_A, "x": 1}
    # Asking for another org's records finds nothing; it never falls back to the own org.
    assert scoped(client, {"org_id": "other"}) == {"$and": [{"org_id": "other"}, {"org_id": ORG_A}]}
    assert scoped(client, {"_id": "other"}, "_id") == {"$and": [{"_id": "other"}, {"_id": ORG_A}]}
    assert scoped(client, {}, "owner_org_id") == {"owner_org_id": ORG_A}
    assert scoped(staff, {"x": 1}) == {"x": 1}
    orphan = User("o", frozenset({"client"}), None, "C", "j")
    assert scoped(orphan, {}) == {"org_id": {"$in": []}}


async def test_verify_requires_the_audience(issuer, clock):
    with pytest.raises(Unauthenticated):
        await verify(issuer.service_token("x"), issuer.keys, clock=clock, audience=ACCESS_AUDIENCE)


async def test_jwks_cache_fetches_once_and_refetches_on_unknown_kid(clock):
    key = SigningKey(Ed25519PrivateKey.generate())
    served = {"keys": [key.jwk]}
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=served)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cache = MemoryStore()
    keys = JwksKeys("http://auth:8000/.well-known/jwks.json", cache, clock, http)
    assert await keys.get(key.kid) is not None
    assert await keys.get(key.kid) is not None
    assert len(calls) == 1
    # A second process finds the keys in Redis without fetching.
    other = JwksKeys("http://auth:8000/.well-known/jwks.json", cache, clock, http)
    assert await other.get(key.kid) is not None
    assert len(calls) == 1
    # Rotation: a new kid is fetched, but no more than once every 30 s.
    new = SigningKey(Ed25519PrivateKey.generate())
    served["keys"].append(new.jwk)
    assert await keys.get(new.kid) is None  # fetched less than 30 s ago
    clock.advance(seconds=31)
    assert await keys.get(new.kid) is not None
    assert await keys.get("forged") is None
    assert len(calls) == 2
    clock.advance(seconds=31)
    assert await keys.get("forged") is None
    assert len(calls) == 3
    token = issue_access(new, clock=clock, user_id="u", roles=["admin"], org_id=None, name="A")
    assert (await verify(token, keys, clock=clock, audience=ACCESS_AUDIENCE))["sub"] == "u"


async def test_static_keys_ignore_other_kids(clock):
    key = SigningKey(Ed25519PrivateKey.generate())
    keys = StaticKeys([key.jwk])
    assert await keys.get(key.kid) is not None
    assert await keys.get("nope") is None


async def test_expiry_uses_the_injected_clock(issuer, clock):
    token = issuer.token("admin", ttl=timedelta(minutes=1))
    assert await verify(token, issuer.keys, clock=clock, audience=ACCESS_AUDIENCE)
    clock.advance(seconds=66)
    with pytest.raises(Unauthenticated):
        await verify(token, issuer.keys, clock=clock, audience=ACCESS_AUDIENCE)
