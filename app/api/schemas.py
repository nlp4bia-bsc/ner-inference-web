"""Public request and job response contracts."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class Submission(BaseModel):
    submitter_name: str = Field(min_length=1, max_length=120)
    submitter_email: EmailStr
    language: str = Field(pattern="^[a-z]{2}$")
    entities: list[str] = Field(min_length=1, max_length=100)

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
    created_at: str
    started_at: str | None
    completed_at: str | None
    expires_at: str | None
    error_summary: str | None
    summary: dict | None
    downloads_available: bool
