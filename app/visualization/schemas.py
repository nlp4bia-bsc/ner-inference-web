"""Bounded, absolute-code-point HTTP visualization contracts."""

from pydantic import BaseModel

from app.domain.annotations import Annotation


class Document(BaseModel):
    document_id: str
    filename: str
    annotation_count: int
    entities_by_label: dict[str, int]
    status: str


class DocumentPage(BaseModel):
    items: list[Document]
    total: int
    offset: int
    limit: int


class TextChunk(BaseModel):
    document_id: str
    filename: str
    text: str
    start: int
    end: int
    total_characters: int


class AnnotationPage(BaseModel):
    items: list[Annotation]
    total: int
    offset: int
    limit: int


class DocumentStatistics(BaseModel):
    document_id: str
    statistics: dict[str, int | float | str | None]


class SearchMatch(BaseModel):
    start: int | None
    end: int | None
    total: int
    wrapped: bool
