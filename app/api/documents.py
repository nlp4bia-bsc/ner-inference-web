"""Paged, token-protected original document and annotation exploration."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.visualization.repository import DocumentRepository
from app.visualization.schemas import (
    AnnotationPage,
    DocumentPage,
    DocumentStatistics,
    SearchMatch,
    TextChunk,
)


def router(service):
    api = APIRouter(prefix="/api/jobs/{token}/documents")
    repository = DocumentRepository(service)

    @api.delete("/{document_id}")
    def delete_document(token: str, document_id: str):
        from app.services.document_management import delete_documents

        return delete_documents(service, token, document_id)

    @api.get("", response_model=DocumentPage)
    def documents(
        token: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        q: Annotated[str, Query(max_length=200)] = "",
        label: str | None = None,
        has_annotations: bool | None = None,
        status: str | None = None,
        sort: str | None = None,
    ):
        rows = [
            r
            for r in repository.index(token)
            if (status is None or r["status"] == status)
            and q.casefold() in r["filename"].casefold()
            and (label is None or label in r["entities_by_label"])
            and (has_annotations is None or bool(r["annotation_count"]) == has_annotations)
        ]
        if sort == "name":
            rows.sort(key=lambda r: r["filename"].casefold())
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "offset": offset,
            "limit": limit,
        }

    @api.get("/{document_id}", response_model=TextChunk)
    def document(
        token: str,
        document_id: str,
        start: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=50000)] = 10000,
    ):
        record, text = repository.text(token, document_id)
        start = min(start, len(text))
        end = min(start + limit, len(text))
        return {
            "document_id": document_id,
            "filename": record["filename"],
            "text": text[start:end],
            "start": start,
            "end": end,
            "total_characters": len(text),
        }

    @api.get("/{document_id}/annotations", response_model=AnnotationPage)
    def annotations(
        token: str,
        document_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        start: Annotated[int, Query(ge=0)] = 0,
        end: Annotated[int | None, Query(ge=0)] = None,
        label: str | None = None,
        q: Annotated[str, Query(max_length=200)] = "",
    ):
        revision, snapshot = repository.annotation_snapshot(token, document_id)
        rows = [
            r
            for r in snapshot
            if r["end"] > start
            and (end is None or r["start"] < end)
            and (label is None or r["label"] == label)
            and q.casefold() in r["text"].casefold()
        ]
        return {
            "revision": revision,
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "offset": offset,
            "limit": limit,
        }

    @api.get("/{document_id}/statistics", response_model=DocumentStatistics)
    def statistics(token: str, document_id: str):
        _, record = repository.document(token, document_id)
        return {"document_id": document_id, "statistics": record["statistics"]}

    @api.get("/{document_id}/search", response_model=SearchMatch)
    def search(
        token: str,
        document_id: str,
        q: Annotated[str, Query(min_length=1, max_length=200)],
        start: Annotated[int, Query(ge=0)] = 0,
    ):
        _, text = repository.text(token, document_id)
        position = text.find(q, start)
        wrapped = position < 0 and start > 0
        if wrapped:
            position = text.find(q)
        return {
            "start": position if position >= 0 else None,
            "end": position + len(q) if position >= 0 else None,
            "total": text.count(q),
            "wrapped": wrapped,
        }

    @api.get("/{document_id}/download/{format}")
    def download_document(token: str, document_id: str, format: str):
        from fastapi.responses import FileResponse, Response

        from app.errors import ServiceError

        root, record = repository.document(token, document_id)
        if format == "txt":
            path = root / "input" / record["filename"]
        elif format == "ann":
            path = root / "published" / document_id / "document.ann"
            if not path.exists():
                path = (root / "output" / "brat" / "documents" / record["filename"]).with_suffix(
                    ".ann"
                )
        else:
            raise ServiceError("Unsupported document download.", 404)
        if format == "ann" and not path.is_file():
            return Response(
                "",
                media_type="text/plain",
                headers={"Content-Disposition": 'attachment; filename="annotations.ann"'},
            )
        from pathlib import PurePosixPath

        name = PurePosixPath(record["filename"]).with_suffix("." + format).name
        return FileResponse(path, filename=name, media_type="text/plain")

    return api
