"""Source-neutral document references persisted at admission; content remains on disk."""

from typing import Literal, TypedDict

SourceType = Literal["PASTED_TEXT", "TXT_UPLOAD", "ZIP_ENTRY"]


class DocumentReference(TypedDict):
    document_id: str
    original_relative_path: str
    source_type: SourceType
    content_reference: str
    size_bytes: int
    status: str
