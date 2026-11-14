"""Settings from the environment. Prefix: MEDIA_ (TRD §16.3)."""

from __future__ import annotations

from mms_common.kafka import KafkaAuth, kafka_auth
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MiB = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEDIA_", extra="ignore")

    service_name: str = "media"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    mongo_db: str = "media"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    # The service's own Kafka user (SASL/SCRAM, TRD §15); required in staging and production.
    kafka_username: str | None = None
    kafka_password: SecretStr | None = None
    # Public signing keys, over the internal network only (TRD §6.1).
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    # /internal/* on auth and operations: a service token, then the owner check (TRD §3.3).
    auth_url: str = "http://auth:8000"
    ops_url: str = "http://operations:8000"
    service_secret: SecretStr = SecretStr("")
    outbox_topic: str = "mms.media.events"
    # Outbox relay, consumers and cron jobs. Off in API tests.
    run_background: bool = True

    # --- Object store (TRD §10). Server-side calls go to `s3_url` on the container network;
    # presigned URLs carry `files_url`, the host the browser uses (the signature covers it).
    s3_url: str = "http://seaweedfs:8333"
    files_url: str = "https://files.mms.localhost"
    s3_access_key: str = ""
    s3_secret_key: SecretStr = SecretStr("")
    bucket_originals: str = "mms-originals"
    bucket_media: str = "mms-media"
    bucket_documents: str = "mms-documents"
    part_size: int = 8 * MiB
    part_url_ttl_s: int = 3600  # upload parts: 1 hour
    get_url_ttl_s: int = 600  # downloads: 10 minutes

    # --- Uploads. The documents path shipped in Phase 2; photos and video joined in Phase 4 (W11).
    enabled_kinds: tuple[str, ...] = ("pdf", "document", "config", "image", "video")
    stale_upload_hours: int = 48  # abort_stale_uploads
    reconcile_after_minutes: int = 15  # re-enqueue media stuck in `uploaded`
    # The worker shares a small host (R7, R8): one video at a time, few threads, a time limit.
    video_threads: int = 2
    video_timeout_s: int = 1800
    work_dir: str = ""  # scratch space for ffmpeg; the system temp folder when empty

    # --- Virus scan (MED-3). `clamd` streams every file to ClamAV; `off` is for hosts too small
    # to run it (staging, TRD T8) and is refused in production. Files then carry
    # `scan_status = skipped`, and staff-only visibility still holds (ADR-19).
    scan_mode: str = "clamd"  # clamd | off
    clamd_host: str = "clamav"
    clamd_port: int = 3310

    @property
    def kafka(self) -> KafkaAuth | None:
        password = self.kafka_password.get_secret_value() if self.kafka_password else None
        return kafka_auth(self.environment, self.kafka_username, password)

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"

    @model_validator(mode="after")
    def _scanning_is_not_optional_in_production(self) -> Settings:
        if self.scan_mode not in ("clamd", "off"):
            raise ValueError("MEDIA_SCAN_MODE must be clamd or off")
        if self.scan_mode == "off" and self.environment == "production":
            raise ValueError("MEDIA_SCAN_MODE=off is not allowed in production (MED-3)")
        return self
