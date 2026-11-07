"""Private import, native bi-encoder/FAISS reuse and language-cache lifecycle."""

import json
import os
import time
import zipfile

import pytest

from app.domain.annotations import canonical_annotations
from app.services.exports.brat import annotation_text
from app.services.normalization import NormalizationCache, NormalizationSession
from app.services.normalization_catalog import NormalizationCatalog
from scripts.import_gazetteers import import_sources


@pytest.fixture
def terminology(settings, tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("faiss")
    from transformers import BertConfig, BertModel, BertTokenizer

    model = tmp_path / "encoder"
    model.mkdir()
    (model / "vocab.txt").write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\ncancer\npain\naspirin\n")
    BertTokenizer(vocab_file=str(model / "vocab.txt")).save_pretrained(model)
    BertModel(
        BertConfig(
            vocab_size=8,
            hidden_size=16,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=24,
        )
    ).save_pretrained(model)
    public = tmp_path / "normalization.yaml"
    public.write_text(f"models:\n  en:\n    - model_dir: {model}\n      pooling: cls\n")
    settings.normalization_model_config_path = public
    settings.normalization_gazetteer_dir = tmp_path / "gazetteers"
    source = tmp_path / "raw" / "en"
    source.mkdir(parents=True)
    pd.DataFrame({"term": ["cancer", "pain"], "code": ["123", "456"]}).to_parquet(
        source / "disease.parquet"
    )
    import_sources(source.parent, settings)
    return settings


def test_native_encoder_index_reuse_and_fallback_preserve_original_offsets(terminology, tmp_path):
    s = terminology
    root = tmp_path / "job"
    root.mkdir()
    errors = []
    span = {
        "filename": "a.txt",
        "label": "DISEASE",
        "text": "cancer",
        "start_span": 2,
        "end_span": 8,
    }
    for expected_hit in (False, True):
        session = NormalizationSession(s, root)
        events = []
        session.on_progress = lambda *args: events.append(args)
        spans = session.normalize([dict(span)], "et", lambda *args: errors.append(args))
        assert ("DISEASE", "NORMALIZING", 1, 1, "mentions") in events
        if expected_hit:
            assert any(event[1] == "LOADING_INDEX" for event in events)
            assert not any(event[1] == "BUILDING_INDEX" for event in events)
        else:
            assert ("DISEASE", "BUILDING_INDEX", 2, 2, "terms") in events
        assert not errors
        result = spans[0]["normalization"]
        assert result["language"] == "en" and result["fallback_to_english"]
        assert result["max_length"] == 256 and result["index"] == "FlatIP"
        assert session.metadata[0]["cache_hit"] is expected_hit
        annotation = canonical_annotations("doc", "  cancer!", spans)[0]
        assert annotation.text == "cancer" and (annotation.start, annotation.end) == (2, 8)
        assert "N1\tReference T1 Terminology:" in annotation_text(spans)
        assert not any("cancer" in p.name for p in s.normalization_cache.rglob("*"))
        session.close()
    assert NormalizationCatalog(s).snapshot("et", ["DISEASE"])[0]["fallback_to_english"]


def test_cache_lru_cap_and_72_hour_idle_expiry(settings):
    cache = NormalizationCache(settings)
    cache.root.mkdir(parents=True)
    for n, language in enumerate(("es", "en", "nl", "sv")):
        path = cache.root / language
        path.mkdir()
        os.utime(path, (time.time() - 100 + n, time.time() - 100 + n))
    cache.sweep()
    assert {p.name for p in cache.root.iterdir() if p.is_dir()} == {"en", "nl", "sv"}
    old = cache.root / "en"
    os.utime(old, (time.time() - 72 * 3600 - 1,) * 2)
    cache.sweep()
    assert not old.exists()


def test_import_rejects_zip_escape_and_never_writes_outside_private_root(settings, tmp_path):
    settings.normalization_gazetteer_dir = tmp_path / "gazetteers"
    source = tmp_path / "bad.zip"
    with zipfile.ZipFile(source, "w") as stream:
        stream.writestr("../secret.parquet", b"invalid")
    with pytest.raises(ValueError, match="Unsafe"):
        import_sources(source, settings)
    assert not (tmp_path / "secret.parquet").exists()
    assert not (settings.normalization_gazetteer_dir / "manifest.json").exists()


def test_missing_terminology_preserves_ner_results(settings, tmp_path):
    settings.normalization_gazetteer_dir = tmp_path / "missing"
    errors = []
    rows = [{"label": "SYMPTOM", "text": "pain", "start_span": 0, "end_span": 4}]
    assert (
        NormalizationSession(settings, tmp_path).normalize(
            rows, "es", lambda *args: errors.append(args)
        )
        == rows
    )
    assert errors[0][2] == "NORMALIZATION"


def test_requested_normalization_is_published_and_exported(terminology):
    from tests.auth_helpers import AccountClient
    from tests.test_document_management import application, execute

    app = application(terminology)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "entities": "DISEASE", "normalize": "true"},
            files=[("files", ("a.txt", b"abc"))],
        )
        assert response.status_code == 202
        identity = response.json()["job_id"]
        execute(app, terminology)
        document = client.get(f"/api/jobs/{identity}/documents").json()["items"][0]
        annotation = client.get(
            f"/api/jobs/{identity}/documents/{document['document_id']}/annotations"
        ).json()["items"][0]
        assert annotation["normalization"]["language"] == "en"
        assert annotation["normalization"]["requested_language"] == "es"
        assert annotation["text"] == "abc" and annotation["end"] == 3
        root = app.state.jobs.storage.job(identity)
        assert (
            '"normalization"'
            in (root / "published" / document["document_id"] / "artifact.json").read_text()
        )
        assert "normalization" in (root / "output" / "annotations.tsv").read_text().splitlines()[0]
        assert (
            "N1\tReference T1"
            in (root / "published" / document["document_id"] / "document.ann").read_text()
        )
        manifest = json.loads((root / "output" / "manifest.json").read_text())
        assert manifest["normalization"]["requested"]


def test_normalization_failure_provenance_survives_batch_reuse_and_deletion(settings, tmp_path):
    from tests.auth_helpers import AccountClient
    from tests.test_document_management import application, execute

    settings.normalization_gazetteer_dir = tmp_path / "missing"
    settings.inference_document_batch_size = 1
    app = application(settings)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "entities": "DISEASE", "normalize": "true"},
            files=[("files", (f"{n}.txt", b"abc")) for n in range(2)],
        )
        assert response.status_code == 202
        identity = response.json()["job_id"]
        execute(app, settings)
        assert app.state.db.get(identity)["status"] == "COMPLETED_WITH_ERRORS"
        documents = client.get(f"/api/jobs/{identity}/documents").json()["items"]
        for document in documents:
            root = app.state.jobs.storage.job(identity)
            record = json.loads(
                (root / "published" / document["document_id"] / "artifact.json").read_text()
            )
            assert record["spans"] and "normalization" not in record["spans"][0]
            assert any(row.get("stage") == "NORMALIZATION" for row in record["models"])
        assert (
            client.delete(
                f"/api/jobs/{identity}/documents/{documents[0]['document_id']}"
            ).status_code
            == 200
        )
        execute(app, settings)
        assert app.state.db.get(identity)["status"] == "COMPLETED_WITH_ERRORS"
        assert client.get(f"/api/jobs/{identity}/documents").json()["total"] == 1
