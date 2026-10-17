"""Settings from the environment. Prefix: PLATFORM_ (TRD §16.3).

platform holds two modules with separate databases and Mongo users (TRD §3.5, rule 1):
`notification` (mongo_uri / mongo_db) and `audit` (audit_mongo_uri / audit_db).
"""

from __future__ import annotations

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

    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    # Public signing keys, over the internal network only (TRD §6.1).
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    # Consumers and cron jobs. Off in API tests.
    run_background: bool = True

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"
