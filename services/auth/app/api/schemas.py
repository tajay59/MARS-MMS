"""Request and response bodies. Requests forbid unknown fields; nothing echoes secrets."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Password = Annotated[str, StringConstraints(max_length=1024)]
Token = Annotated[str, StringConstraints(min_length=20, max_length=200)]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Role = Literal["client", "technician", "admin", "viewer"]
ThemeName = Literal["system", "light", "dark"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Requests ------------------------------------------------------------------------------


class RegisterIn(In):
    name: Name
    email: Email
    phone: Phone | None = None
    password: Password
    # Typed by the client; the admin links it to an organization at approval (AFD J1).
    organization_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class LoginIn(In):
    email: Annotated[str, StringConstraints(max_length=254)]
    password: Password


class ResetRequestIn(In):
    email: Annotated[str, StringConstraints(max_length=254)]


class ResetConfirmIn(In):
    token: Token
    password: Password


class AcceptInvitationIn(In):
    token: Token
    password: Password


class MePatch(In):
    name: Name | None = None
    phone: Phone | None = None
    time_zone: Annotated[str, StringConstraints(max_length=64)] | None = None
    theme: ThemeName | None = None
    current_password: Password | None = None
    new_password: Password | None = None


class InviteIn(In):
    email: Email
    name: Name
    roles: Annotated[list[Role], Field(min_length=1, max_length=4)]
    org_id: Id | None = None
    phone: Phone | None = None


class UserPatch(In):
    version: int
    name: Name | None = None
    phone: Phone | None = None
    roles: Annotated[list[Role], Field(min_length=1, max_length=4)] | None = None
    org_id: Id | None = None
    status: Literal["active", "disabled"] | None = None


class OrgIn(In):
    name: OrgName
    country: Country
    contact_email: Email | None = None
    phone: Phone | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class OrgPatch(In):
    version: int
    name: OrgName | None = None
    country: Country | None = None
    contact_email: Email | None = None
    phone: Phone | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    status: Literal["active", "inactive"] | None = None


class ApproveIn(In):
    version: int | None = None
    org_id: Id | None = None
    new_organization: OrgIn | None = None


class RejectIn(In):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AccountLinkIn(In):
    kind: Literal["reset", "invitation"]
    id: Id


Hex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class MaterialTheme(In):
    """Brand colours from a Material Theme Builder export: the light and dark schemes (every
    Material 3 role) and the five tonal palettes. app.domain.branding checks the exact keys."""

    name: Annotated[str, StringConstraints(max_length=120)] | None = None
    seed: Hex | None = None
    schemes: dict[Literal["light", "dark"], dict[str, Hex]]
    palettes: dict[
        Literal["primary", "secondary", "tertiary", "neutral", "neutral-variant"], dict[str, Hex]
    ]


class BrandingIn(In):
    """`material: null` goes back to the built-in colours. `version` is what the admin saw."""

    material: MaterialTheme | None
    version: Annotated[int, Field(ge=0)]


# --- Responses -----------------------------------------------------------------------------


class Me(BaseModel):
    id: str
    email: str
    name: str
    phone: str | None
    roles: list[str]
    org_id: str | None
    time_zone: str | None
    theme: str
    status: str

    @classmethod
    def of(cls, doc: dict[str, Any]) -> Me:
        return cls(
            id=doc["_id"],
            email=doc["email"],
            name=doc["name"],
            phone=doc.get("phone"),
            roles=list(doc["roles"]),
            org_id=doc.get("org_id"),
            time_zone=doc.get("time_zone"),
            theme=doc.get("theme", "system"),
            status=doc["status"],
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 - the scheme name
    expires_in: int
    # When the refresh cookie expires: the PWA's offline_until for the PIN session (§6.1).
    refresh_expires_at: datetime
    user: Me


class Accepted(BaseModel):
    status: str


class UserOut(Me):
    proposed_org_name: str | None
    rejection_reason: str | None
    last_login_at: datetime | None
    created_at: datetime
    version: int

    @classmethod
    def of(cls, doc: dict[str, Any]) -> UserOut:
        return cls(
            **Me.of(doc).model_dump(),
            proposed_org_name=doc.get("proposed_org_name"),
            rejection_reason=doc.get("rejection_reason"),
            last_login_at=doc.get("last_login_at"),
            created_at=doc["created_at"],
            version=doc["version"],
        )


class UserPage(BaseModel):
    items: list[UserOut]
    next_after: str | None


class OrgOut(BaseModel):
    id: str
    name: str
    country: str
    contact_email: str | None
    phone: str | None
    address: str | None
    status: str
    version: int

    @classmethod
    def of(cls, doc: dict[str, Any]) -> OrgOut:
        return cls(
            id=doc["_id"],
            name=doc["name"],
            country=doc["country"],
            contact_email=doc.get("contact_email"),
            phone=doc.get("phone"),
            address=doc.get("address"),
            status=doc["status"],
            version=doc["version"],
        )


class OrgPage(BaseModel):
    items: list[OrgOut]
    next_after: str | None


class AccountLinkOut(BaseModel):
    url: str
    email: str
    name: str
    expires_at: datetime


class BrandingOut(BaseModel):
    """The colours everyone sees. `material` is null for the built-in colours; `version` is 0
    until an admin first saves."""

    material: MaterialTheme | None
    version: int
    updated_at: datetime | None

    @classmethod
    def of(cls, doc: dict[str, Any] | None) -> BrandingOut:
        if doc is None:
            return cls(material=None, version=0, updated_at=None)
        material = doc.get("material")
        return cls(
            material=MaterialTheme.model_validate(material) if material else None,
            version=doc["version"],
            updated_at=doc["updated_at"],
        )


class ServiceTokenOut(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 - the scheme name
    expires_in: int
