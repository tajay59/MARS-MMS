"""Settings from the environment. Prefix: OPS_ (TRD §16.3)."""

from __future__ import annotations

from mms_common.kafka import KafkaAuth, kafka_auth
from pydantic import SecretStr, model_validator
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

    # Client Review (REQ-13, REQ-14; W18-4, W18-8). Days may be fractions so a staging check
    # needs no calendar; production refuses anything under a day.
    client_attestation: str = (
        "I confirm that the work described in the reports above has been completed, "
        "and I accept it."
    )
    review_reminder_days: str = "7,21,28"
    auto_close_days: float = 30.0
    review_clock_every_s: float = 900.0
    signature_max_bytes: int = 100 * 1024
    signature_max_width: int = 1200
    signature_max_height: int = 600

    @model_validator(mode="after")
    def _review_period_is_sane(self) -> Settings:
        days = self.reminder_days
        if self.auto_close_days <= 0 or any(d <= 0 for d in days):
            raise ValueError("review days must be above zero")
        if any(d >= self.auto_close_days for d in days):
            raise ValueError("every reminder must come before the auto-close day")
        if self.environment == "production" and (
            self.auto_close_days < 1 or any(d < 1 for d in days)
        ):
            raise ValueError("production keeps the review periods at a day or more")
        return self

    @property
    def reminder_days(self) -> tuple[float, ...]:
        parts = [p.strip() for p in self.review_reminder_days.split(",") if p.strip()]
        return tuple(sorted({float(p) for p in parts}))

    @property
    def kafka(self) -> KafkaAuth | None:
        password = self.kafka_password.get_secret_value() if self.kafka_password else None
        return kafka_auth(self.environment, self.kafka_username, password)

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"
