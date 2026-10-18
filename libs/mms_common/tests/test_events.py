from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from mms_common.events import SCHEMAS, Envelope, Resource, UnknownEvent, register, validate


def make(type_="widget.approved", version=1, data=None):
    return Envelope(
        event_id="0192f0c4-0000-7000-8000-000000000001",
        type=type_,
        version=version,
        occurred_at=datetime(2026, 10, 16, tzinfo=UTC),
        source="auth",
        key="u1",
        aggregate_version=1,
        resource=Resource(type="user", id="u1"),
        data=data or {},
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    before = dict(SCHEMAS)
    yield
    SCHEMAS.clear()
    SCHEMAS.update(before)


def test_valid_payload_passes():
    @register("widget.approved")
    class Approved(BaseModel):
        user_id: str

    assert validate(make(data={"user_id": "u1"})).user_id == "u1"


def test_unknown_type_is_rejected_for_the_dlq():
    with pytest.raises(UnknownEvent):
        validate(make(type_="nope.happened"))


def test_unknown_version_is_rejected():
    @register("widget.approved", 1)
    class V1(BaseModel):
        user_id: str

    with pytest.raises(UnknownEvent):
        validate(make(version=2))


def test_invalid_payload_is_rejected():
    @register("widget.approved")
    class Approved(BaseModel):
        user_id: str

    with pytest.raises(ValidationError):
        validate(make(data={}))


def test_duplicate_registration_fails():
    @register("widget.approved")
    class A(BaseModel):
        pass

    with pytest.raises(ValueError):

        @register("widget.approved")
        class B(BaseModel):
            pass


def test_auth_schemas_are_registered_on_import():
    for type_ in ("auth.login_succeeded", "auth.login_failed", "user.registered", "user.invited",
                  "user.approved", "user.rejected", "user.updated", "user.disabled", "org.created",
                  "org.updated", "auth.password_reset_requested", "auth.token_reuse_detected",
                  "branding.updated"):
        assert (type_, 1) in SCHEMAS, type_


def test_auth_events_never_carry_secrets():
    """Reset and invitation links are minted on send; no event schema has a token field."""
    for (type_, _), model in SCHEMAS.items():
        for name in model.model_fields:
            assert not any(word in name for word in ("token", "password", "secret", "hash")) or (
                name == "email_hash"
            ), f"{type_}.{name}"
