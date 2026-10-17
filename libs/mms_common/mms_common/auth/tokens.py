"""EdDSA (Ed25519) JWTs: issued by auth, verified by every service (TRD §6.1, ADR-7).

Nginx does not check tokens, so each service verifies them itself. Verification accepts
only `alg: EdDSA` with a known `kid`, the right audience and issuer, and an unexpired `exp`
read from the injectable clock. Access and service tokens have different audiences, so one
can never be used as the other.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Protocol

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from mms_common.errors import Unauthenticated
from mms_common.ids import new_id
from mms_common.time import Clock

ALGORITHM = "EdDSA"
ISSUER = "aws-mms-auth"
ACCESS_AUDIENCE = "aws-mms"
SERVICE_AUDIENCE = "aws-mms-internal"
ACCESS_TTL = timedelta(minutes=15)
SERVICE_TTL = timedelta(minutes=5)
LEEWAY_S = 5  # clock skew between containers on one host is small


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def public_jwk(public_key: Ed25519PublicKey) -> dict[str, str]:
    """The JWKS entry for a key. `kid` is its RFC 7638 thumbprint."""
    x = _b64url(public_key.public_bytes(Encoding.Raw, PublicFormat.Raw))
    canonical = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"))
    kid = _b64url(hashlib.sha256(canonical.encode()).digest())
    return {"kty": "OKP", "crv": "Ed25519", "x": x, "kid": kid, "alg": ALGORITHM, "use": "sig"}


def public_key_from_jwk(jwk: Mapping[str, Any]) -> Ed25519PublicKey:
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise ValueError("not an Ed25519 key")
    x = str(jwk["x"])
    return Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(x + "=" * (-len(x) % 4)))


class SigningKey:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self.private_key = private_key
        self.jwk = public_jwk(private_key.public_key())
        self.kid = self.jwk["kid"]


def issue_access(
    key: SigningKey,
    *,
    clock: Clock,
    user_id: str,
    roles: list[str],
    org_id: str | None,
    name: str,
    ttl: timedelta = ACCESS_TTL,
) -> str:
    now = clock.now()
    claims = {
        "iss": ISSUER,
        "aud": ACCESS_AUDIENCE,
        "sub": user_id,
        "roles": sorted(roles),
        "org_id": org_id,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": new_id(),
    }
    return jwt.encode(claims, key.private_key, algorithm=ALGORITHM, headers={"kid": key.kid})


def issue_service(
    key: SigningKey, *, clock: Clock, service: str, ttl: timedelta = SERVICE_TTL
) -> str:
    now = clock.now()
    claims = {
        "iss": ISSUER,
        "aud": SERVICE_AUDIENCE,
        "sub": service,
        "roles": ["service"],
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": new_id(),
    }
    return jwt.encode(claims, key.private_key, algorithm=ALGORITHM, headers={"kid": key.kid})


class KeySource(Protocol):
    async def get(self, kid: str) -> Ed25519PublicKey | None: ...


class StaticKeys:
    """Keys known up front: auth's own keys, and the test issuer's."""

    def __init__(self, jwks: list[Mapping[str, Any]]) -> None:
        self._keys = {str(k["kid"]): public_key_from_jwk(k) for k in jwks}

    async def get(self, kid: str) -> Ed25519PublicKey | None:
        return self._keys.get(kid)


async def verify(token: str, keys: KeySource, *, clock: Clock, audience: str) -> dict[str, Any]:
    """Return the claims of a valid token, or raise `Unauthenticated`."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Invalid token") from exc
    # Checked before any key lookup: rules out `none` and HS256-with-the-public-key confusion.
    if header.get("alg") != ALGORITHM:
        raise Unauthenticated("Invalid token")
    kid = header.get("kid")
    key = await keys.get(kid) if isinstance(kid, str) else None
    if key is None:
        raise Unauthenticated("Invalid token")
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=audience,
            issuer=ISSUER,
            # Expiry is checked below against the injectable clock (TRD §17).
            options={
                "require": ["exp", "iat", "sub", "jti"],
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Invalid token") from exc
    now = clock.now().timestamp()
    if not isinstance(claims["exp"], int) or claims["exp"] + LEEWAY_S < now:
        raise Unauthenticated("Token expired", reason="token_expired")
    if not isinstance(claims["iat"], int) or claims["iat"] - LEEWAY_S > now:
        raise Unauthenticated("Invalid token")
    return claims
