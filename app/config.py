from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True, hide_input_in_errors=True
    )
    storage_root: Path = Path("storage")
    model_config_path: Path = Path("catalog/models.yaml")
    model_validation_path: Path = Path("catalog/validated-models.json")
    public_base_url: str = "https://localhost:8000"
    app_prefix: str = ""
    device: str = "auto"
    worker_concurrency: int = 1
    max_documents_per_job: int | None = Field(None, ge=1)
    job_results_ttl_hours: float = Field(72, gt=0)
    rate_limit_seconds: int = Field(60, ge=1)
    max_upload_mb: float = Field(50, gt=0)
    max_uncompressed_mb: float = Field(250, gt=0)
    max_document_mb: float = Field(5, gt=0)
    max_zip_entries: int = Field(5000, ge=1)
    max_compression_ratio: float = Field(100, gt=0)
    max_queue_size: int = Field(100, ge=1)
    max_storage_mb: float = Field(10000, gt=0)
    min_free_disk_mb: float = Field(500, ge=0)
    max_concurrent_uploads: int = Field(4, ge=1)
    inference_document_batch_size: int = Field(32, ge=1, le=1000)
    max_loaded_models: int = Field(2, ge=1, le=32)
    storage_reserve_factor: float = Field(4, ge=1)
    storage_reserve_extra_mb: float = Field(32, ge=1)
    max_attempts: int = Field(2, ge=1)
    job_timeout_seconds: int = Field(7200, ge=1)
    cleanup_interval_seconds: int = Field(60, ge=1)
    tombstone_hours: float = Field(24, gt=0)

    app_env: str = "production"
    cookie_secure: bool = True
    session_max_seconds: int = Field(43200, ge=60)
    session_idle_seconds: int = Field(1800, ge=30)
    verification_seconds: int = Field(86400, ge=60)
    reset_seconds: int = Field(1800, ge=60)
    auth_rate_window_seconds: int = Field(900, ge=1)
    auth_rate_email_attempts: int = Field(10, ge=1)
    auth_rate_ip_attempts: int = Field(60, ge=1)
    audit_retention_days: int = Field(365, ge=1)
    mail_backend: str = "none"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_starttls: bool = True

    @property
    def cookie_path(self):
        # __Host cookies forbid Domain injection and require Path=/ even under /ner.
        return "/" if self.cookie_secure else self.app_prefix or "/"

    @property
    def session_cookie(self):
        if not self.cookie_secure:
            return "temu_session"
        import hashlib

        suffix = (
            "_" + hashlib.sha256(self.app_prefix.encode()).hexdigest()[:8]
            if self.app_prefix
            else ""
        )
        return "__Host-temu" + suffix + "_session"

    @model_validator(mode="after")
    def sequential(self):
        if self.app_prefix and (
            not self.app_prefix.startswith("/")
            or self.app_prefix.endswith("/")
            or ".." in self.app_prefix
            or "//" in self.app_prefix
        ):
            raise ValueError("APP_PREFIX must be empty or an absolute path without trailing slash")
        from urllib.parse import urlsplit

        if self.app_env not in ("production", "development", "test"):
            raise ValueError("APP_ENV must be production, development or test")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("Production requires Secure cookies")
        if self.mail_backend not in ("none", "smtp", "memory", "file"):
            raise ValueError("Unsupported mail backend")
        if self.app_env == "production" and self.mail_backend in ("memory", "file"):
            raise ValueError("Local capture mail backends are forbidden in production")
        origin = urlsplit(self.public_base_url)
        if (
            origin.scheme not in ("http", "https")
            or not origin.hostname
            or origin.path.rstrip("/") != self.app_prefix
        ):
            raise ValueError("PUBLIC_BASE_URL must include exactly APP_PREFIX")
        if self.app_env == "production" and origin.scheme != "https":
            raise ValueError("Production requires an HTTPS public origin")
        if origin.username or origin.password or origin.query or origin.fragment:
            raise ValueError("PUBLIC_BASE_URL must be a trusted origin and prefix")
        if not self.cookie_secure and origin.hostname not in (
            "localhost",
            "127.0.0.1",
            "testserver",
        ):
            raise ValueError("Insecure development cookies require a loopback/test origin")
        if self.worker_concurrency != 1:
            raise ValueError("This single-host queue requires WORKER_CONCURRENCY=1")
        return self

    @property
    def upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024**2)

    @property
    def db_path(self) -> Path:
        return self.storage_root / "jobs.sqlite3"
