"""Kafka credentials (TRD §15): SCRAM options for aiokafka, and no unauthenticated broker
outside local and test."""

import pytest

from mms_common.kafka import KafkaAuth, kafka_auth


def test_scram_options_for_aiokafka():
    assert KafkaAuth("auth", "s3cret").options() == {
        "security_protocol": "SASL_PLAINTEXT",
        "sasl_mechanism": "SCRAM-SHA-512",
        "sasl_plain_username": "auth",
        "sasl_plain_password": "s3cret",
    }


def test_the_password_stays_out_of_logs():
    assert "s3cret" not in repr(KafkaAuth("auth", "s3cret"))


def test_credentials_when_given():
    assert kafka_auth("staging", "auth", "s3cret") == KafkaAuth("auth", "s3cret")


@pytest.mark.parametrize("environment", ["local", "test"])
def test_no_credentials_means_an_open_broker_locally(environment):
    assert kafka_auth(environment, None, None) is None


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize(("username", "password"), [(None, None), ("auth", None), (None, "x")])
def test_staging_and_production_refuse_to_start_without_them(environment, username, password):
    with pytest.raises(ValueError, match="required"):
        kafka_auth(environment, username, password)
