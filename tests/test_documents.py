import io
import stat
import zipfile

import pytest

from app.errors import ServiceError
from app.services.documents import load_documents, safe_name


def zipped(rows, compression=zipfile.ZIP_STORED):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression) as archive:
        for name, data in rows:
            archive.writestr(name, data)
    return [("corpus.zip", target.getvalue())]


@pytest.mark.parametrize(
    "files",
    [
        [("a.txt", b"abc")],
        [("a.txt", b"abc"), ("b.txt", b"def")],
        zipped([("a.txt", b"abc")]),
        zipped([("one/a.txt", b"abc"), ("two/a.txt", b"def")]),
    ],
)
def test_valid(files, settings):
    assert load_documents(files, settings)


def test_preserve_unicode_crlf(settings):
    text = "á😀\r\nCanción\tfin.\n"
    assert load_documents([("á.txt", text.encode())], settings)["á.txt"] == text.encode()


@pytest.mark.parametrize(
    "name",
    [
        "../a.txt",
        "/a.txt",
        "a/../b.txt",
        "a//b.txt",
        "C:/a.txt",
        "a\\b.txt",
        "./a.txt",
        "a\x00.txt",
        "a\n.txt",
        "a./b.txt",
    ],
)
def test_unsafe_paths(name):
    with pytest.raises(ServiceError):
        safe_name(name)


@pytest.mark.parametrize(
    "files",
    [
        [("a.txt", b"")],
        [("a.txt", b" \n")],
        [("a.txt", b"\xff")],
        [("a.txt", b"a\0b")],
        [("a.pdf", b"abc")],
        [("a.zip", b"bad")],
        [("a.txt", b"a"), ("a.txt", b"b")],
        [("A.txt", b"a"), ("a.txt", b"b")],
        zipped([("nested.zip", b"abc")]),
        zipped([("../evil.txt", b"abc")]),
        zipped([("a.txt", b"a"), ("a.txt/b.txt", b"b")]),
    ],
)
def test_rejected(files, settings):
    with pytest.raises(ServiceError):
        load_documents(files, settings)


@pytest.mark.parametrize("count,accepted", [(1000, True), (1001, False)])
def test_document_limit(count, accepted, settings):
    settings = settings.model_copy(update={"max_documents_per_job": 1000})
    files = zipped([(f"folder/{i}.txt", b"abc") for i in range(count)])
    if accepted:
        assert len(load_documents(files, settings)) == 1000
    else:
        with pytest.raises(ServiceError):
            load_documents(files, settings)


def test_zip_bomb(settings):
    with pytest.raises(ServiceError):
        load_documents(zipped([("a.txt", b"a" * 200000)], zipfile.ZIP_DEFLATED), settings)


def test_symlink(settings):
    info = zipfile.ZipInfo("link.txt")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ServiceError):
        load_documents(zipped([(info, b"/etc/passwd")]), settings)


def test_sizes_and_entries(settings):
    for update, files in [
        ({"max_upload_mb": 0.000001}, [("a.txt", b"abc")]),
        ({"max_document_mb": 0.000001}, [("a.txt", b"abc")]),
        ({"max_uncompressed_mb": 0.000001}, zipped([("a.txt", b"abc")])),
        ({"max_zip_entries": 1}, zipped([("a.txt", b"abc"), ("b.txt", b"abc")])),
    ]:
        with pytest.raises(ServiceError):
            load_documents(files, settings.model_copy(update=update))
