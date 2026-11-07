"""Mixed DT4H/UMLS metadata canonicalizes before any terminology is prepared."""

import json
import zipfile

import pytest

from app.services.normalization_catalog import NormalizationCatalog
from scripts.gazetteer_metadata import normalize_language
from scripts.import_gazetteers import import_sources


@pytest.mark.parametrize(
    "value,expected",
    [
        (" SPA ", "es"),
        ("ENG", "en"),
        ("CZE", "cs"),
        ("CES", "cs"),
        ("DUT", "nl"),
        ("NLD", "nl"),
        ("ITA", "it"),
        ("RUM", "ro"),
        ("RON", "ro"),
        ("SWE", "sv"),
        ("es-ES", "es"),
        ("es_419", "es"),
        ("Spanish", "es"),
        ("Español", "es"),
        (["SPA"], "es"),
        ("['SPA']", "es"),
        (["es", "SPA"], "es"),
        (["SPA", "ENG"], None),
        (None, None),
        ("not a language", None),
    ],
)
def test_language_aliases_are_explicit_and_ambiguous_cells_are_rejected(value, expected):
    pytest.importorskip("pandas")
    assert normalize_language(value) == expected


def test_28_translations_follow_folder_despite_stale_source_language(settings, tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    settings.normalization_gazetteer_dir = tmp_path / "private"
    source = tmp_path / "source"
    archive = tmp_path / "dt4h_gazs.zip"
    with zipfile.ZipFile(archive, "w") as target:
        for language in ("es", "en", "cs", "nl", "it", "ro", "sv"):
            folder = source / language
            folder.mkdir(parents=True)
            for category in ("disease", "medications", "procedure", "symptom"):
                row = {
                    "language": ["ENG" if category == "medications" else "es"],
                    "code": ["C0001" if category == "medications" else "123"],
                    "term": [[f"{language} term", f"{language} synonym"]],
                }
                if category == "medications":
                    row.update(SAB=["SNOMEDCT_US"], SAB_code=["111"])
                path = folder / (category + ".parquet")
                pd.DataFrame(row).to_parquet(path)
                target.write(path, "dt4h_gazs/parquet/" + language + "/" + path.name)
    result = import_sources(archive, settings)
    assert len(result) == 28
    assert {row["language"] for row in result} == {"es", "en", "cs", "nl", "it", "ro", "sv"}
    for row in result:
        assert row["rows"] == 2
        if row["entity"] == "MEDICATION":
            assert row["code_system"] == "UMLS"
    for row in result:
        prepared = pd.read_parquet(settings.normalization_gazetteer_dir / row["path"])
        assert len(prepared) == 2
        assert all(term.startswith(row["language"] + " ") for term in prepared["term"])
    alternative = settings.model_copy(
        update={"normalization_gazetteer_dir": tmp_path / "column-authority"}
    )
    merged = import_sources(archive, alternative, language_source="column")
    assert len(merged) == 4 and {row["language"] for row in merged} == {"es", "en"}
    catalog = NormalizationCatalog(settings)
    assert catalog.resolve("es", "MEDICATION")["resolved_language"] == "es"


def test_arrow_list_metadata_and_explicit_overrides(settings, tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    settings.normalization_gazetteer_dir = tmp_path / "private"
    source = tmp_path / "medications.parquet"
    pd.DataFrame(
        {
            "language": [["SPA"], ["es"]],
            "entity": [["drugs"], ["MEDICATION"]],
            "code": ["C1", "C2"],
            "term": ["one", "two"],
        }
    ).to_parquet(source)
    assert import_sources(source, settings)[0]["language"] == "es"
    result = import_sources(source, settings, language="ENG", entity="DISEASE")
    assert any(row["language"] == "en" and row["entity"] == "DISEASE" for row in result)


def test_preflight_reports_all_invalid_files_without_terms_or_partial_registration(
    settings, tmp_path, caplog, capsys
):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    settings.normalization_gazetteer_dir = tmp_path / "private"
    source = tmp_path / "source" / "es"
    source.mkdir(parents=True)
    for name, lang in (
        ("disease", "es"),
        ("medications", "PRIVATE_INVALID_LANGUAGE"),
        ("symptom", "unknown"),
    ):
        pd.DataFrame(
            {"language": [lang], "code": ["123"], "term": ["PRIVATE_DICTIONARY_VALUE"]}
        ).to_parquet(source / (name + ".parquet"))
    with pytest.raises(ValueError, match="No terminology has been registered") as error:
        import_sources(source.parent, settings, language_source="column")
    assert "medications.parquet" in str(error.value) and "symptom.parquet" in str(error.value)
    assert "PRIVATE" not in str(error.value)
    assert "stage=PREPARED" not in caplog.text
    assert not (settings.normalization_gazetteer_dir / "manifest.json").exists()
    import_sources(source.parent, settings, inspect=True, language_source="column")
    output = capsys.readouterr().out
    reports = [json.loads(line) for line in output.splitlines()]
    assert reports[0]["metadata"]["languages"] == ["es"]
    assert sum(row["metadata"]["invalid_language_rows"] for row in reports) == 2
    assert "PRIVATE" not in output


def test_inspect_remains_usable_when_filename_cannot_identify_metadata(settings, tmp_path, capsys):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    settings.normalization_gazetteer_dir = tmp_path / "private"
    source = tmp_path / "unknown.parquet"
    pd.DataFrame({"term": ["PRIVATE_VALUE"], "code": ["123"]}).to_parquet(source)
    import_sources(source, settings, inspect=True)
    result = json.loads(capsys.readouterr().out)
    assert (
        result["metadata"]["invalid_language_rows"]
        == result["metadata"]["invalid_entity_rows"]
        == 1
    )
