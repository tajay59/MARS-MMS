"""Settings from the environment. Prefix: OPS_ (TRD §16.3)."""

from __future__ import annotations

from mms_common.kafka import KafkaAuth, kafka_auth
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPS_", extra="ignore")

    service_name: str = "operations"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    mongo_db: str = "operations"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    # The service's own Kafka user (SASL/SCRAM, TRD §15); required in staging and production.
    kafka_username: str | None = None
    kafka_password: SecretStr | None = None
    # Public signing keys, over the internal network only (TRD §6.1).
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    # /internal/* on auth: a service token from /internal/service-token, then the
    # organizations snapshot (TRD §6.4, §8.6).
    auth_url: str = "http://auth:8000"
    service_secret: SecretStr = SecretStr("")
    # media's /internal/* routes: file checks and download links (TRD §3.2, §3.3).
    media_url: str = "http://media:8000"
    outbox_topic: str = "mms.operations.events"
    # Outbox relay, consumers and cron jobs. Off in API tests.
    run_background: bool = True

    @property
    def kafka(self) -> KafkaAuth | None:
        password = self.kafka_password.get_secret_value() if self.kafka_password else None
        return kafka_auth(self.environment, self.kafka_username, password)

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"
