"""Request and response bodies. Requests forbid unknown fields; nothing echoes secrets."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from mms_common.ids import UUID7_PATTERN
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain import recovery

Id = Annotated[str, StringConstraints(pattern=UUID7_PATTERN)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Password = Annotated[str, StringConstraints(max_length=1024)]
Token = Annotated[str, StringConstraints(min_length=20, max_length=200)]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# The short name for tables and chips (an acronym), and the organization's ID in the system its data
# was imported from, used to match its stations on import (decision W5-8)
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
ExternalId = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._:-]{1,64}$")
]
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
    # The app can show the second step. Without it, a person who needs one is told to reload the
    # app instead of being sent a challenge it can't read (W22, "Old clients").
    supports_mfa: bool = False


Code = Annotated[str, StringConstraints(min_length=6, max_length=12)]
RecoveryCode = Annotated[str, StringConstraints(min_length=10, max_length=24)]


class OneFactor(In):
    """A code from the authenticator app, or one recovery code: exactly one."""

    code: Code | None = None
    recovery_code: RecoveryCode | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> OneFactor:
        if (self.code is None) == (self.recovery_code is None):
            raise ValueError("Give either code or recovery_code")
        return self


class LoginTotpIn(OneFactor):
    challenge: Token


class EnrolBeginIn(In):
    challenge: Token


class EnrolConfirmIn(In):
    challenge: Token
    code: Code


class TotpBeginIn(In):
    password: Password


class TotpConfirmIn(In):
    code: Code


class TotpProofIn(OneFactor):
    """Changing the second factor takes the password and a current code."""

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
    short_name: ShortName | None = None
    external_id: ExternalId | None = None
    country: Country
    contact_email: Email | None = None
    phone: Phone | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class OrgPatch(In):
    version: int
    name: OrgName | None = None
    short_name: ShortName | None = None
    external_id: ExternalId | None = None
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


class UserLookupIn(In):
    ids: list[Id] = Field(min_length=1, max_length=50)


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
    totp_enabled: bool = False
    recovery_codes_left: int = 0

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
            totp_enabled=bool(doc.get("totp")),
            recovery_codes_left=recovery.remaining(doc.get("recovery_codes")),
        )


class MfaSetup(BaseModel):
    """The person's role needs a second factor and they have none yet: the app shows a banner
    until `required_by`, after which sign-in goes through enrolment."""

    required_by: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 - the scheme name
    expires_in: int
    # When the refresh cookie expires: the PWA's offline_until for the PIN session (§6.1).
    refresh_expires_at: datetime
    user: Me
    mfa_setup: MfaSetup | None = None
    # Shown once, only in the answer that finishes an enrolment at sign-in.
    recovery_codes: list[str] | None = None


class MfaChallenge(BaseModel):
    """A correct password is not a session yet. `enrol`: they must set up a second factor first."""

    mfa_required: Literal[True] = True
    enrol: bool = False
    challenge: str
    expires_in: int


class TotpSetupOut(BaseModel):
    """Shown once, while the person adds the account to their authenticator app."""

    secret: str
    otpauth_uri: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


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
    short_name: str | None
    external_id: str | None
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
            short_name=doc.get("short_name"),
            external_id=doc.get("external_id"),
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


class UserRefOut(BaseModel):
    """What another service may know about a person: never an email, phone or organization."""

    id: str
    name: str
    roles: list[str]
    status: str


class UserLookupOut(BaseModel):
    users: list[UserRefOut]


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
