"""Original-document annotation contracts, independent of drawing and export formats."""

from pydantic import BaseModel, Field


class Annotation(BaseModel):
    id: str
    document_id: str
    label: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str
    score: float | None = Field(default=None, ge=0, le=1)
    model_id: str | None = None


def validate_surface(text: str, start: int, end: int, surface: str) -> None:
    if not 0 <= start < end <= len(text) or text[start:end] != surface:
        raise ValueError("Annotation offsets do not round-trip against original text")


def canonical_annotations(document_id: str, text: str, spans: list[dict]) -> list[Annotation]:
    annotations = []
    for index, row in enumerate(spans, 1):
        validate_surface(text, row["start_span"], row["end_span"], row["text"])
        annotations.append(
            Annotation(
                id=f"T{index}",
                document_id=document_id,
                label=row["label"],
                start=row["start_span"],
                end=row["end_span"],
                text=row["text"],
                score=row.get("score"),
                model_id=row.get("model_id"),
            )
        )
    return annotations
