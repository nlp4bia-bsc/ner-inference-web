"""Exact and true normalized Levenshtein matching without neural execution."""

import json

import pytest

from app.domain.annotations import canonical_annotations
from app.services.normalization import NormalizationSession
from app.services.normalization_catalog import NormalizationCatalog
from scripts.import_gazetteers import import_sources
from tests.auth_helpers import AccountClient
from tests.test_document_management import application, execute
from tests.test_normalization import terminology as terminology


def span(text="cancer"):
    return {
        "filename": "a.txt",
        "label": "DISEASE",
        "text": text,
        "start_span": 2,
        "end_span": 2 + len(text),
    }


def test_default_lexical_never_prepares_encoder_and_reuses_cache(
    terminology, tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Neural execution is forbidden in lexical mode")

    monkeypatch.setattr(NormalizationSession, "_encoder", forbidden)
    monkeypatch.setattr("sqlite3.connect", forbidden)
    errors = []
    for _ in range(2):
        session = NormalizationSession(terminology, tmp_path)
        result = session.normalize([span("CANCER")], "es", lambda *args: errors.append(args))
        assert not errors
        normalized = result[0]["normalization"]
        assert normalized["method"] == "levenshtein" and normalized["score"] == 1
        assert normalized["model"] is None and normalized["max_length"] is None
        assert normalized["code"] == "123" and normalized["fallback_to_english"]
        assert session.encoder is None and session.models is None
        assert session.metadata[0]["cache_hit"] is False
        assert session.metadata[0]["pairs"] == session.metadata[0]["concepts"] == 2
        annotation = canonical_annotations("doc", "😀 CANCER!", result)[0]
        assert annotation.text == "CANCER" and (annotation.start, annotation.end) == (2, 8)
        session.normalize([span("CANCER")], "es", lambda *args: errors.append(args))
        assert session.metadata[-1]["cache_hit"]
        session.close()
    assert not terminology.hub_cache.exists()
    assert not terminology.normalization_cache.exists()


@pytest.mark.parametrize(
    "method,threshold,matched",
    [("levenshtein", 0.8, True), ("levenshtein", 0.9, False), ("exact", 0.8, False)],
)
def test_edit_similarity_threshold_and_valid_misses(
    terminology, tmp_path, method, threshold, matched
):
    session = NormalizationSession(terminology, tmp_path, method=method, threshold=threshold)
    errors = []
    result = session.normalize([span("cancxr")], "es", lambda *args: errors.append(args))
    assert not errors and session.last_completed_entities == {"DISEASE"}
    assert bool(result[0].get("normalization")) is matched
    if matched:
        assert result[0]["normalization"]["score"] == pytest.approx(5 / 6)
    session.close()


def test_lexical_works_without_any_encoder_configuration(terminology, tmp_path):
    catalog = NormalizationCatalog(terminology)
    catalog.models = {}
    session = NormalizationSession(terminology, tmp_path, catalog, method="exact")
    errors = []
    assert (
        session.normalize([span()], "en", lambda *args: errors.append(args))[0]["normalization"][
            "code"
        ]
        == "123"
    )
    assert not errors
    session.close()


def test_streamed_fuzzy_ranking_matches_brute_force_unique_concepts(terminology, tmp_path):
    import pandas as pd
    from rapidfuzz.distance import Levenshtein

    source = tmp_path / "disease.parquet"
    terms = [f"form-{i:05d}" for i in range(4500)]
    codes = [f"C{i % 100:03d}" for i in range(4500)]
    pd.DataFrame({"term": terms, "code": codes, "language": "en"}).to_parquet(source)
    import_sources(source, terminology)
    query = "form-0xx99"
    expected = {}
    for term, code in zip(terms, codes, strict=True):
        score = Levenshtein.normalized_similarity(query, term)
        if score >= 0.8 and (
            code not in expected
            or (-score, term) < (-expected[code]["score"], expected[code]["term"])
        ):
            expected[code] = {"term": term, "code": code, "score": score}
    ranked = sorted(expected.values(), key=lambda row: (-row["score"], row["code"], row["term"]))[
        :5
    ]
    session = NormalizationSession(terminology, tmp_path)
    errors = []
    result = session.normalize([span(query)], "en", lambda *args: errors.append(args))
    assert not errors and ranked
    actual = result[0]["normalization"]["candidates"]
    assert [(row["code"], row["term"], row["score"]) for row in actual] == [
        (row["code"], row["term"], row["score"]) for row in ranked
    ]
    session.close()


def test_default_job_completes_when_lexical_mentions_do_not_match(terminology, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Encoder must be explicitly selected")

    monkeypatch.setattr(NormalizationSession, "_encoder", forbidden)
    app = application(terminology)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "entities": "DISEASE", "normalize": "true"},
            files=[("files", ("a.txt", b"abc"))],
        )
        identity = response.json()["job_id"]
        payload = json.loads(app.state.db.get(identity)["payload"])
        assert (
            payload["normalization_method"] == "levenshtein"
            and payload["normalization_threshold"] == 0.8
        )
        assert "models" not in payload["normalization_resources"][0]
        execute(app, terminology)
        assert app.state.db.get(identity)["status"] == "COMPLETED"
        progress = client.get(f"/api/jobs/{identity}/progress").json()
        assert progress["models"][1]["status"] == "COMPLETED"
        assert progress["models"][1]["method"] == "levenshtein"


def test_higher_threshold_removes_an_earlier_normalization(terminology, tmp_path):
    first = NormalizationSession(terminology, tmp_path, threshold=0.8)
    spans = first.normalize([span("cancxr")], "en", lambda *args: None)
    assert spans[0].get("normalization")
    first.close()
    second = NormalizationSession(terminology, tmp_path, threshold=0.9)
    second.normalize(spans, "en", lambda *args: None)
    assert "normalization" not in spans[0]
    second.close()


def test_explicit_bi_encoder_keeps_loaded_index_across_batches(terminology, tmp_path, monkeypatch):
    session = NormalizationSession(terminology, tmp_path, method="bi_encoder")
    errors = []
    session.normalize([span("cancer")], "en", lambda *args: errors.append(args))
    assert not errors

    def forbidden(*args, **kwargs):
        raise AssertionError("Index was already loaded for this entity")

    monkeypatch.setattr(session.cache, "load_or_build", forbidden)
    session.normalize([span("pain")], "en", lambda *args: errors.append(args))
    assert not errors and session.metadata[-1]["cache_hit"]
    session.close()


@pytest.mark.parametrize("method", ["exact", "levenshtein", "bi_encoder"])
def test_api_persists_explicit_method_and_threshold(terminology, method):
    app = application(terminology)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={
                "language": "es",
                "entities": "DISEASE",
                "normalize": "true",
                "normalization_method": method,
                "normalization_threshold": "0.87",
            },
            files=[("files", ("a.txt", b"abc"))],
        )
        assert response.status_code == 202, response.text
        saved = json.loads(app.state.db.get(response.json()["job_id"])["payload"])
        assert saved["normalization_method"] == method and saved["normalization_threshold"] == 0.87
        assert ("models" in saved["normalization_resources"][0]) is (method == "bi_encoder")


@pytest.mark.parametrize(
    "field,value",
    [
        ("normalization_method", "anything"),
        ("normalization_threshold", "-0.1"),
        ("normalization_threshold", "1.1"),
        ("normalization_threshold", "NaN"),
    ],
)
def test_api_rejects_invalid_normalization_options(terminology, field, value):
    app = application(terminology)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "entities": "DISEASE", "normalize": "true", field: value},
            files=[("files", ("a.txt", b"abc"))],
        )
        assert response.status_code == 422


def test_old_queued_job_defaults_to_lexical_without_implicit_encoder(terminology, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Old queued request must not implicitly build FAISS")

    monkeypatch.setattr(NormalizationSession, "_encoder", forbidden)
    app = application(terminology)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={
                "language": "es",
                "entities": "DISEASE",
                "normalize": "true",
                "normalization_method": "bi_encoder",
            },
            files=[("files", ("a.txt", b"abc"))],
        )
        identity = response.json()["job_id"]
        payload = json.loads(app.state.db.get(identity)["payload"])
        payload.pop("normalization_method")
        payload.pop("normalization_threshold")
        with app.state.db.connect() as connection:
            connection.execute(
                "UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), identity)
            )
        execute(app, terminology)
        saved = app.state.db.get(identity)
        assert saved["status"] == "COMPLETED"
        assert json.loads(saved["payload"])["normalization_method"] == "levenshtein"
        assert (
            client.get(f"/api/jobs/{identity}/progress").json()["models"][1]["method"]
            == "levenshtein"
        )


@pytest.mark.parametrize("threshold,matched", [(0, True), (0.8, True), (1, False)])
def test_inclusive_edit_boundary_and_legacy_parquet_keys(terminology, tmp_path, threshold, matched):
    import pandas as pd

    from app.services.lexical_normalization import LexicalMatcher
    from app.services.normalization_catalog import file_sha256

    source = tmp_path / "legacy.parquet"
    pd.DataFrame({"term": ["abcde", "ABCde"], "code": ["A", "B"]}).to_parquet(source)
    matcher = LexicalMatcher({"file": source, "sha256": file_sha256(source)}, lambda *args: None)
    assert not matcher.metadata["precomputed_keys"]
    results = matcher.match(["abcdx"], "levenshtein", threshold, 5, lambda *args: None)[0]
    assert bool(results) is matched
    if matched:
        assert [row["code"] for row in results] == ["A", "B"]
        assert all(row["score"] == 0.8 for row in results)
    exact = matcher.match(["ＡＢＣＤＥ"], "exact", 1, 5, lambda *args: None)[0]
    assert [row["code"] for row in exact] == ["A", "B"]
    matcher.close()


def test_lexical_exports_and_deletion_repackage_without_current_dictionary(terminology, tmp_path):
    import pandas as pd

    source = tmp_path / "disease.parquet"
    pd.DataFrame({"term": ["abc"], "code": ["123"], "language": ["en"]}).to_parquet(source)
    import_sources(source, terminology, code_system="SNOMEDCT")
    app = application(terminology)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "entities": "DISEASE", "normalize": "true"},
            files=[("files", (name, b"abc")) for name in ("a.txt", "b.txt")],
        )
        identity = response.json()["job_id"]
        execute(app, terminology)
        documents = client.get(f"/api/jobs/{identity}/documents").json()["items"]
        annotation = client.get(
            f"/api/jobs/{identity}/documents/{documents[0]['document_id']}/annotations"
        ).json()["items"][0]
        assert annotation["normalization"]["method"] == "levenshtein"
        assert annotation["normalization"]["model"] is None
        assert annotation["normalization"]["code"] == "123"
        assert (annotation["start"], annotation["end"], annotation["text"]) == (0, 3, "abc")
        root = app.state.jobs.storage.job(identity)
        assert (
            "SNOMEDCT:123"
            in (root / "published" / documents[0]["document_id"] / "document.ann").read_text()
        )
        assert "levenshtein" in (root / "output" / "annotations.tsv").read_text()
        assert (
            client.delete(
                f"/api/jobs/{identity}/documents/{documents[0]['document_id']}"
            ).status_code
            == 200
        )
        for path in terminology.normalization_gazetteer_dir.rglob("*.parquet"):
            path.unlink()
        execute(app, terminology)
        assert app.state.db.get(identity)["status"] == "COMPLETED"
        manifest = json.loads((root / "output" / "manifest.json").read_text())
        assert manifest["normalization"]["methods_in_results"] == ["levenshtein"]
