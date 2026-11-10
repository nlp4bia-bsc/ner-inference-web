"""Public request and job response contracts."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.identity import EmailAddress


class Submission(BaseModel):
    submitter_name: str = Field(min_length=1, max_length=120)
    submitter_email: EmailAddress
    language: str = Field(pattern="^(?:[a-z]{2}|oth)$")
    other_language: str = Field(default="", max_length=100)
    job_name: str = Field(default="", max_length=200)
    entities: list[str] = Field(default_factory=list, max_length=100)
    normalize: bool = False
    normalization_method: Literal["exact", "levenshtein", "bi_encoder"] = "levenshtein"
    normalization_threshold: float = Field(0.8, ge=0, le=1, allow_inf_nan=False)
    models: list[str] | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("job_name", "other_language")
    @classmethod
    def clean_description(cls, value: str) -> str:
        import unicodedata

        if any(unicodedata.category(c) == "Cc" for c in value):
            raise ValueError("Use a single line of text")
        return value.strip()

    @model_validator(mode="after")
    def check_other_language(self):
        if self.language == "oth" and not self.other_language:
            raise ValueError("Specify the document language for Other")
        if self.language != "oth":
            self.other_language = ""
        return self

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
    job_name: str = ""
    other_language: str = ""
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
    models: list[dict] = Field(default_factory=list)
    worker: dict = Field(default_factory=dict)
    inference_percent: float = 0
    publication_revision: float = 0

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


class DocumentReference(BaseModel):
    job_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)


class DocumentSelection(BaseModel):
    documents: list[DocumentReference] = Field(min_length=1, max_length=1000)
