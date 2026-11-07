"""Synthetic DT4H-like list cells and UMLS/source identifiers; no private data."""

import json
import zipfile

import pytest

from app.services.normalization_catalog import NormalizationCatalog
from app.services.normalization_diagnostics import normalization_status
from scripts.gazetteer_values import term_code_pairs
from scripts.import_gazetteers import import_sources


def test_list_pairing_preserves_alignment_nulls_and_rejects_guessing():
    pytest.importorskip("pandas")
    assert list(term_code_pairs(["a", "b"], "123")) == [("a", "123"), ("b", "123")]
    assert list(term_code_pairs("a", ["1", "2"])) == [("a", "1"), ("a", "2")]
    assert list(term_code_pairs(["a", "b"], [None, "2"], "aligned")) == [("b", "2")]
    assert list(term_code_pairs(["a", "b", "a"], ["1", "2", "3"], "aligned")) == [
        ("a", "1"),
        ("b", "2"),
        ("a", "3"),
    ]
    assert list(term_code_pairs('["a","b"]', "['123']")) == [("a", "123"), ("b", "123")]
    with pytest.raises(ValueError, match="No association"):
        list(term_code_pairs(["a", "b"], ["1", "2"]))
    assert len(list(term_code_pairs(["a", "b"], ["1", "2"], "all"))) == 4


@pytest.mark.parametrize("source_column", ["SAB_code", "code_SAB"])
def test_dt4h_zip_list_synonyms_and_umls_identifiers(settings, tmp_path, source_column, capsys):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    settings.normalization_gazetteer_dir = tmp_path / "private"
    root = tmp_path / "source"
    root.mkdir()
    pd.DataFrame(
        {
            "language": ["es"],
            "code": ["123"],
            "term": [["cancer", "neoplasm"]],
            "semantic_tag": ["disorder"],
            "mainterm": ["cancer"],
        }
    ).to_parquet(root / "disease.parquet")
    pd.DataFrame(
        {
            "language": ["es", "es"],
            "code": ["C0001", "C0001"],
            "term": [["aspirin", "aspirina"], ["aspirin"]],
            "SAB": ["SNOMEDCT_US", "ATC"],
            source_column: ["111", "B01AC06"],
        }
    ).to_parquet(root / "medications.parquet")
    archive = tmp_path / "dt4h_gazs.zip"
    with zipfile.ZipFile(archive, "w") as target:
        for path in root.glob("*.parquet"):
            target.write(path, "dt4h/es/" + path.name)
    assert normalization_status(settings)["import_required"]
    import_sources(archive, settings, inspect=True)
    inspection = capsys.readouterr().out
    assert '"types"' in inspection and "list" in inspection and "aspirin" not in inspection
    imported = import_sources(archive, settings)
    assert len(imported) == 2
    catalog = NormalizationCatalog(settings)
    medication = catalog.resolve("es", "MEDICATION")
    assert medication["code_system"] == "UMLS"
    frame = pd.read_parquet(medication["file"])
    assert set(frame["code"]) == {"C0001"}
    refs = json.loads(frame.loc[frame.term == "aspirin", "references"].iloc[0])
    assert refs == [
        {"code_system": "ATC", "code": "B01AC06"},
        {"code_system": "SNOMEDCT_US", "code": "111"},
    ]
    assert len(pd.read_parquet(catalog.resolve("es", "DISEASE")["file"])) == 2
    assert not normalization_status(settings)["import_required"]
    assert not list(settings.normalization_gazetteer_dir.glob(".import-*"))
