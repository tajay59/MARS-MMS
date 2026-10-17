from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from mms_common.events import SCHEMAS, Envelope, Resource, UnknownEvent, register, validate


def make(type_="user.approved", version=1, data=None):
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
    @register("user.approved")
    class Approved(BaseModel):
        user_id: str

    assert validate(make(data={"user_id": "u1"})).user_id == "u1"


def test_unknown_type_is_rejected_for_the_dlq():
    with pytest.raises(UnknownEvent):
        validate(make(type_="nope.happened"))


def test_unknown_version_is_rejected():
    @register("user.approved", 1)
    class V1(BaseModel):
        user_id: str

    with pytest.raises(UnknownEvent):
        validate(make(version=2))


def test_invalid_payload_is_rejected():
    @register("user.approved")
    class Approved(BaseModel):
        user_id: str

    with pytest.raises(ValidationError):
        validate(make(data={}))


def test_duplicate_registration_fails():
    @register("user.approved")
    class A(BaseModel):
        pass

    with pytest.raises(ValueError):

        @register("user.approved")
        class B(BaseModel):
            pass
