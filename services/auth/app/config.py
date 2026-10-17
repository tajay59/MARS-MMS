"""Settings from the environment. Prefix: AUTH_ (TRD §16.3)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    service_name: str = "auth"
    environment: str = "local"  # local | staging | production
    log_level: str = "INFO"

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    mongo_db: str = "auth"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    # Not used by auth itself (it verifies with its own keys); kept for the template's shape.
    auth_jwks_url: str = "http://auth:8000/.well-known/jwks.json"
    outbox_topic: str = "mms.auth.events"
    # Outbox relay and cron jobs. Off in API tests.
    run_background: bool = True

    # Ed25519 private key (PEM, PKCS8). A Docker secret in staging and production. Deploying a
    # new file rotates the key: the old public key stays in JWKS for a day (TRD §6.1).
    signing_key_file: str = "/run/secrets/auth_signing_key"
    # Per-service secrets for /internal/service-token, as JSON: {"platform": "..."} (§6.4).
    service_secrets: dict[str, str] = {}

    # Public origin of the app, for links in account emails.
    app_url: str = "https://mms.localhost"
    cookie_secure: bool = True

    refresh_ttl_days: int = 30
    refresh_grace_s: int = 30
    reset_ttl_s: int = 3600
    invitation_ttl_days: int = 7
    pending_purge_days: int = 30  # AUTH-5
    login_max_failures: int = 5
    login_lock_s: int = 900
    reset_requests_per_hour: int = 3

    # Breached-password check (AUTH-9, T1): "hibp" (k-anonymity range API, falling back to the
    # local file when unreachable), "file" (local SHA-1 list only) or "off" (tests only).
    breached_check: str = "hibp"
    breached_file: str | None = None
    hibp_url: str = "https://api.pwnedpasswords.com/range/"
    hibp_timeout_s: float = 3.0

    # Argon2id (TRD §6.2: at least time=3, memory=64 MiB).
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    argon2_parallelism: int = 4

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI at /docs is off in production; the schema is exported in CI."""
        return self.environment != "production"
