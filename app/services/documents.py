"""Bounded ZIP reading; original bytes and character offsets remain unchanged."""

import io
import stat
import zipfile
from pathlib import PurePosixPath

from app.config import Settings
from app.domain.documents import DocumentReference, SourceType
from app.errors import ServiceError


def safe_name(name: str) -> str:
    if not name or "\\" in name or ":" in name or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ServiceError("Invalid filename.")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or any(x in (".", "..", "") for x in name.split("/"))
        or len(name.encode()) > 500
    ):
        raise ServiceError("Unsafe or excessively long file path.")
    # Reserve exporter config names and avoid trailing-dot aliases on other filesystems.
    if any(len(x.encode()) > 200 or x.endswith((".", " ")) for x in path.parts):
        raise ServiceError("Unsupported file path.")
    return str(path)


def iter_documents(files, s: Settings):
    documents: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    sizes = []
    for _, stream in files:
        stream.seek(0, 2)
        sizes.append(stream.tell())
        stream.seek(0)
    if not files or sum(sizes) > s.upload_bytes:
        raise ServiceError("The upload exceeds the configured limit.", 413)
    is_zip = len(files) == 1 and files[0][0].lower().endswith(".zip")

    def add(name: str, data: bytes):
        nonlocal total
        name = safe_name(name)
        if not name.endswith(".txt"):
            raise ServiceError("Only .txt documents or a single ZIP are allowed.")
        # Reject case-fold aliases as well as exact duplicates, preserving original names.
        if name.casefold() in seen:
            raise ServiceError("Duplicate document paths are not allowed.")
        if any(str(parent) in documents for parent in PurePosixPath(name).parents) or any(
            existing.startswith(name + "/") for existing in documents
        ):
            raise ServiceError("Conflicting file and directory paths.")
        seen.add(name.casefold())
        if len(documents) >= s.max_documents_per_job:
            raise ServiceError(
                f"A request may contain at most {s.max_documents_per_job} documents."
            )
        total += len(data)
        if len(data) > s.max_document_mb * 1024**2 or total > s.max_uncompressed_mb * 1024**2:
            raise ServiceError("Documents exceed the uncompressed size limit.", 413)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ServiceError("All documents must be UTF-8 text.") from None
        if not text.strip():
            raise ServiceError("Empty documents are not supported.")
        if any(ord(c) < 32 and c not in "\t\n\r" for c in text) or "\x7f" in text:
            raise ServiceError("Binary content is not allowed in text documents.")
        documents[name] = True
        return name, data

    if not is_zip:
        for name, stream in files:
            yield add(name, stream.read(int(s.max_document_mb * 1024**2) + 1))
    else:
        try:
            with zipfile.ZipFile(files[0][1]) as archive:
                infos = archive.infolist()
                if len(infos) > s.max_zip_entries:
                    raise ServiceError("Too many ZIP entries.")
                if sum(x.file_size for x in infos) > s.max_uncompressed_mb * 1024**2:
                    raise ServiceError("ZIP uncompressed size exceeds the limit.", 413)
                entry_names = set()
                for info in infos:
                    name = safe_name(info.filename.rstrip("/") if info.is_dir() else info.filename)
                    if name.casefold() in entry_names:
                        raise ServiceError("Duplicate ZIP paths are not allowed.")
                    entry_names.add(name.casefold())
                    mode = info.external_attr >> 16
                    if (
                        stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                        or info.flag_bits & 1
                    ):
                        raise ServiceError("Links, special or encrypted files are not supported.")
                    if info.is_dir():
                        continue
                    if (
                        info.file_size > s.max_document_mb * 1024**2
                        or info.file_size / max(info.compress_size, 1) > s.max_compression_ratio
                    ):
                        raise ServiceError(
                            "ZIP compression ratio or document size exceeds the limit.", 413
                        )
                    if not name.endswith(".txt"):
                        raise ServiceError(
                            "ZIP may contain only TXT files and folders; nested ZIPs are not supported."
                        )
                    with archive.open(info) as f:
                        data = f.read(int(s.max_document_mb * 1024**2) + 1)
                    yield add(name, data)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError):
            raise ServiceError("The ZIP file is corrupt or uses an unsupported format.") from None
    if not documents:
        raise ServiceError("No text documents were found.")
    paths = set(documents)
    if any(str(parent) in paths for name in paths for parent in PurePosixPath(name).parents):
        raise ServiceError("Conflicting file and directory paths.")
    return documents


def load_documents(files: list[tuple[str, bytes]], s: Settings) -> dict[str, bytes]:
    """Compatibility helper for controlled in-memory callers; HTTP uses file streams."""
    return dict(iter_documents([(name, io.BytesIO(data)) for name, data in files], s))


def ingest(
    files, destination, s: Settings, source_type: SourceType, on_bytes=None
) -> list[DocumentReference]:
    from app.visualization.repository import document_id

    references: list[DocumentReference] = []
    total = 0
    for name, data in iter_documents(files, s):
        total += len(data)
        if on_bytes:
            on_bytes(total)
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            for offset in range(0, len(data), 65536):
                out.write(data[offset : offset + 65536])
        references.append(
            {
                "document_id": document_id(name),
                "original_relative_path": name,
                "source_type": source_type,
                "content_reference": "input/" + name,
                "size_bytes": len(data),
                "status": "PENDING",
            }
        )
    return references
