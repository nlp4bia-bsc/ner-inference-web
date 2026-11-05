from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    storage_root: Path = Path("storage")
    model_config_path: Path = Path("catalog/models.yaml")
    model_validation_path: Path = Path("catalog/validated-models.json")
    public_base_url: str = "http://localhost:8000"
    app_prefix: str = ""
    device: str = "auto"
    worker_concurrency: int = 1
    max_documents_per_job: int = Field(1000, ge=1)
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
    max_attempts: int = Field(2, ge=1)
    job_timeout_seconds: int = Field(7200, ge=1)
    cleanup_interval_seconds: int = Field(60, ge=1)
    tombstone_hours: float = Field(24, gt=0)

    @model_validator(mode="after")
    def sequential(self):
        if self.app_prefix and (
            not self.app_prefix.startswith("/")
            or self.app_prefix.endswith("/")
            or ".." in self.app_prefix
            or "//" in self.app_prefix
        ):
            raise ValueError("APP_PREFIX must be empty or an absolute path without trailing slash")
        if self.worker_concurrency != 1:
            raise ValueError("This single-host queue requires WORKER_CONCURRENCY=1")
        return self

    @property
    def upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024**2)

    @property
    def db_path(self) -> Path:
        return self.storage_root / "jobs.sqlite3"
