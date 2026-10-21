"""Settings from the environment. Prefix: PLATFORM_ (TRD §16.3).

platform holds two modules with separate databases and Mongo users (TRD §3.5, rule 1):
`notification` (mongo_uri / mongo_db) and `audit` (audit_mongo_uri / audit_db).
"""

from __future__ import annotations

from typing import Literal

from mms_common.kafka import KafkaAuth, kafka_auth
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLATFORM_", extra="ignore")

    service_name: str = "platform"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    # notification module (account emails in W4; WebSocket and in-app notifications, Phase 3).
    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    mongo_db: str = "notification"
    # audit module: its own user, which can't update or delete audit_events (TRD §12).
    audit_mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    audit_db: str = "audit"
    # Every producer's topic (TRD §8.1). platform produces none.
    audit_topics: list[str] = [
        "mms.auth.events",
        "mms.operations.events",
        "mms.media.events",
        "mms.report.events",
    ]

    # The notification consumer's topics: auth for accounts, operations for requests and comments.
    notification_topics: list[str] = ["mms.auth.events", "mms.operations.events"]
    # A socket's token is checked again this often (TRD 13.4 says 25 s).
    ws_heartbeat_s: float = 25.0

    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    # The service's own Kafka user (SASL/SCRAM, TRD §15); required in staging and production.
    kafka_username: str | None = None
    kafka_password: SecretStr | None = None
    # Public signing keys, over the internal network only (TRD §6.1).
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    # /internal/* on auth: service token from /internal/service-token, then account links.
    auth_url: str = "http://auth:8000"
    service_secret: SecretStr = SecretStr("")
    # Consumers and cron jobs. Off in API tests.
    run_background: bool = True

    # Account emails (NOT-3). Mailpit locally; the organization's relay (T3) elsewhere.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_security: Literal["none", "starttls", "ssl"] = "none"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    mail_from: str = "MARS-MMS <no-reply@mms.localhost>"
    # Where the links in emails point: the app's public address.
    app_url: str = "https://mms.localhost"
    email_poll_s: float = 5.0

    @property
    def kafka(self) -> KafkaAuth | None:
        password = self.kafka_password.get_secret_value() if self.kafka_password else None
        return kafka_auth(self.environment, self.kafka_username, password)

    @model_validator(mode="after")
    def _relay_is_encrypted(self) -> Settings:
        if self.environment == "production" and self.smtp_security == "none":
            raise ValueError("PLATFORM_SMTP_SECURITY must be starttls or ssl in production")
        return self

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"
