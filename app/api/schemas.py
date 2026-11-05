"""Public request and job response contracts."""

from pydantic import BaseModel, Field, field_validator

from app.domain.identity import EmailAddress


class Submission(BaseModel):
    submitter_name: str = Field(min_length=1, max_length=120)
    submitter_email: EmailAddress
    language: str = Field(pattern="^[a-z]{2}$")
    entities: list[str] = Field(default_factory=list, max_length=100)
    models: list[str] | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("submitter_name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Enter your name")
        return value.strip()

    @field_validator("submitter_email", mode="after")
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class JobAccepted(BaseModel):
    job_id: str
    status: str
    token: str
    url: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    document_count: int
    processed_documents: int
    queue_position: int | None
    language: str
    entities: list[str]
    models: list[str] = Field(default_factory=list)
    created_at: str
    started_at: str | None
    completed_at: str | None
    expires_at: str | None
    error_summary: str | None
    summary: dict | None
    server_now: str
    progress: dict
    downloads_available: bool


class ProgressResponse(BaseModel):
    status: str
    stage: str
    total_documents: int
    annotated_documents: int
    processing_documents: int
    failed_documents: int
    pending_documents: int
    progress_percent: float
    updated_at: str
    server_now: str
    expires_at: str | None
    queue_position: int | None
    provisional_statistics: dict[str, int | None]
    mentions: int
    partial_results: bool
