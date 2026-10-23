"""Settings from the environment. Prefix: REPORT_ (TRD §16.3)."""

from __future__ import annotations

from mms_common.kafka import KafkaAuth, kafka_auth
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPORT_", extra="ignore")

    service_name: str = "report"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    mongo_db: str = "report"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    # The service's own Kafka user (SASL/SCRAM, TRD §15); required in staging and production.
    kafka_username: str | None = None
    kafka_password: SecretStr | None = None
    # Public signing keys, over the internal network only (TRD §6.1).
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    # /internal/* on operations, with a service token from auth (TRD §6.4).
    auth_url: str = "http://auth:8000"
    ops_url: str = "http://operations:8000"
    media_url: str = "http://media:8000"
    service_secret: SecretStr = SecretStr("")
    outbox_topic: str = "mms.report.events"
    # Outbox relay and consumers. Off in API tests.
    run_background: bool = True

    # --- Object store (TRD §10). Server-side calls go to `s3_url` on the container network;
    # presigned download links carry `files_url`, the host the browser uses.
    s3_url: str = "http://seaweedfs:8333"
    files_url: str = "https://files.mms.localhost"
    s3_access_key: str = ""
    s3_secret_key: SecretStr = SecretStr("")
    bucket_reports: str = "mms-reports"
    get_url_ttl_s: int = 600  # downloads: 10 minutes

    # --- Rendering (TRD §11.1)
    # The address a QR label points at: `<app_url>/s/<token>`.
    app_url: str = "https://mms.localhost"
    # Printed on label sheets when the request gives none (QR-6). Empty prints no phone line.
    label_contact_phone: str = ""
    job_max_attempts: int = 3
    # --- Visit report drafts (W16-5, W16-6)
    # How long a draft waits for the visit's photos and video to be processed before its first
    # PDF is drawn with what is ready (TRD 3.4: five minutes)
    draft_wait_s: int = 300
    draft_tick_s: int = 30  # how often the cron reads stale facts and queues first PDFs

    @property
    def kafka(self) -> KafkaAuth | None:
        password = self.kafka_password.get_secret_value() if self.kafka_password else None
        return kafka_auth(self.environment, self.kafka_username, password)

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"
