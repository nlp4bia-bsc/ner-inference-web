"""Import confidential local Parquet dictionaries; contents never enter Git or logs."""

import argparse
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from app.config import Settings
from app.domain.normalization_references import merge_reference_values
from app.services.lexical_normalization import KEY_FORMAT, normalized_form
from app.services.normalization_catalog import CATEGORIES, file_sha256
from scripts.gazetteer_metadata import (
    LANGUAGE_ALIASES,
    LANGUAGE_NAMES,
    normalize_entity,
    normalize_language,
    normalize_series,
)
from scripts.gazetteer_values import deduplicate_pairs, prepare_pairs

ENTITY_NAMES = {
    "medication": "MEDICATION",
    "medications": "MEDICATION",
    "drug": "MEDICATION",
    "drugs": "MEDICATION",
    "farmaco": "MEDICATION",
    "medicamento": "MEDICATION",
    "procedure": "PROCEDURE",
    "procedures": "PROCEDURE",
    "procedimiento": "PROCEDURE",
    "medprocner": "PROCEDURE",
    "proctemist": "PROCEDURE",
    "disease": "DISEASE",
    "diseases": "DISEASE",
    "enfermedad": "DISEASE",
    "distemist": "DISEASE",
    "disorder": "DISEASE",
    "disorders": "DISEASE",
    "symptom": "SYMPTOM",
    "symptoms": "SYMPTOM",
    "sintoma": "SYMPTOM",
    "symptemist": "SYMPTOM",
}
TERM_COLUMNS = (
    "term",
    "text",
    "mention",
    "synonym",
    "name",
    "description",
    "label",
    "string",
    "str",
)
CODE_COLUMNS = (
    "code",
    "cui",
    "concept_id",
    "conceptid",
    "concept_code",
    "snomed_code",
    "snomed_id",
    "umls_code",
    "id",
)


def named_column(columns, requested, alternatives):
    if requested:
        if requested not in columns:
            raise ValueError("Explicit column not found: " + requested)
        return requested
    lowered = {name.lower(): name for name in columns}
    for name in alternatives:
        if name in lowered:
            return lowered[name]
    raise ValueError("Required column not found; use explicit --term-column/--code-column")


def guess_language(path):
    tokens = re.split(r"[^a-z]+", str(path).lower())
    matches = {
        LANGUAGE_NAMES.get(token, LANGUAGE_ALIASES.get(token, token))
        for token in tokens
        if token in LANGUAGE_NAMES
        or token in LANGUAGE_ALIASES
        or token
        in {
            "es",
            "en",
            "ca",
            "cs",
            "nl",
            "ro",
            "sv",
            "it",
            "el",
            "fr",
            "pt",
            "de",
            "da",
            "no",
            "et",
            "ru",
        }
    }
    if len(matches) != 1:
        raise ValueError("Language is ambiguous; provide --language or a language column")
    return matches.pop()


def guess_entity(path):
    tokens = re.split(r"[^a-z]+", str(path).lower())
    matches = {ENTITY_NAMES[token] for token in tokens if token in ENTITY_NAMES}
    if len(matches) != 1:
        raise ValueError("Entity type is ambiguous; provide --entity or an entity column")
    return matches.pop()


def source_files(source, temporary):
    if source.is_dir():
        return sorted(
            path
            for path in source.rglob("*.parquet")
            if ".prepared" not in path.parts
            and not any(part.startswith(".import-") for part in path.parts)
        )
    if source.suffix.lower() == ".parquet":
        return [source]
    if source.suffix.lower() != ".zip":
        raise ValueError("Source must be a Parquet file, ZIP or directory")
    with zipfile.ZipFile(source) as archive:
        for entry in archive.infolist():
            relative = PurePosixPath(entry.filename.replace("\\", "/"))
            mode = entry.external_attr >> 16
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
                or ":" in relative.parts[0]
                or stat.S_ISLNK(mode)
                or entry.flag_bits & 1
            ):
                raise ValueError("Unsafe terminology ZIP entry")
            if entry.is_dir() or relative.suffix.lower() != ".parquet":
                continue
            if shutil.disk_usage(temporary).free < entry.file_size + 32 * 1024**2:
                raise ValueError("Insufficient disk space for terminology import")
            target = temporary.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source_stream, target.open("wb") as output:
                shutil.copyfileobj(source_stream, output, 1024 * 1024)
    return sorted(temporary.rglob("*.parquet"))


def metadata_columns(schema, language_column=None, entity_column=None):
    lower = {name.lower(): name for name in schema.names}
    language = language_column or next(
        (lower[key] for key in ("language", "lang", "lat") if key in lower), None
    )
    entity = entity_column or next(
        (
            lower[key]
            for key in ("entity", "entity_type", "category", "semantic_group")
            if key in lower
        ),
        None,
    )
    for selected in (language, entity):
        if selected and selected not in schema.names:
            raise ValueError("Explicit metadata column not found")
    return language, entity


def inferred_metadata(guess, relative):
    try:
        return guess(relative)
    except ValueError:
        return None


def classify_metadata(frame, relative, language, entity, lc, ec, language_source="auto"):
    path_language = inferred_metadata(guess_language, relative)
    if language:
        languages = normalize_language(language)
    elif language_source == "path" or (language_source == "auto" and path_language):
        languages = path_language
    elif lc:
        languages = normalize_series(frame[lc], normalize_language)
    else:
        languages = path_language
    entities = (
        normalize_entity(entity, ENTITY_NAMES)
        if entity
        else normalize_series(frame[ec], lambda value: normalize_entity(value, ENTITY_NAMES))
        if ec
        else inferred_metadata(guess_entity, relative)
    )
    return frame.assign(_language=languages, _entity=entities)


def metadata_summary(frame):
    invalid_language = frame["_language"].isna()
    invalid_entity = ~frame["_entity"].isin(CATEGORIES)
    return {
        "languages": sorted(frame["_language"].dropna().unique().tolist()),
        "entities": sorted(frame.loc[~invalid_entity, "_entity"].unique().tolist()),
        "invalid_language_rows": int(invalid_language.sum()),
        "invalid_entity_rows": int(invalid_entity.sum()),
    }


def import_sources(
    source,
    settings,
    language=None,
    entity=None,
    term_column=None,
    code_column=None,
    language_column=None,
    entity_column=None,
    code_system=None,
    inspect=False,
    list_pairing=None,
    language_source="auto",
):
    import pandas as pd
    import pyarrow.parquet as pq

    root = settings.normalization_gazetteer_dir.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as folder:
        temporary = Path(folder)
        paths = source_files(Path(source).resolve(), temporary)
        if not paths:
            raise ValueError("No Parquet terminology files found")

        def relative_path(path):
            return (
                path.relative_to(temporary)
                if path.is_relative_to(temporary)
                else path.relative_to(Path(source).resolve())
                if Path(source).is_dir()
                else path.name
            )

        plans = []
        errors = []
        for index, path in enumerate(paths, 1):
            if not inspect:
                logging.getLogger("temu.import").info(
                    "terminology_import file=%s/%s stage=CHECKING_METADATA", index, len(paths)
                )
            schema = pq.read_schema(path)
            lc, ec = metadata_columns(schema, language_column, entity_column)
            # Preflight metadata alone for every file; vocabulary values are never printed.
            columns = list(dict.fromkeys(column for column in (lc, ec) if column))
            metadata = (
                pd.read_parquet(path, columns=columns, dtype_backend="pyarrow")
                if columns
                else pd.DataFrame(index=range(pq.ParquetFile(path).metadata.num_rows))
            )
            classified = classify_metadata(
                metadata, relative_path(path), language, entity, lc, ec, language_source
            )
            summary = metadata_summary(classified)
            path_language = inferred_metadata(guess_language, relative_path(path))
            summary["path_language"] = path_language
            summary["language_source"] = (
                "explicit"
                if language
                else "path"
                if language_source == "path" or (language_source == "auto" and path_language)
                else "column"
            )
            summary["column_languages"] = (
                sorted(
                    normalize_series(metadata[lc], normalize_language).dropna().unique().tolist()
                )
                if lc
                else []
            )
            if inspect:
                print(
                    json.dumps(
                        {
                            "file": path.name,
                            "relative_path": str(relative_path(path)),
                            "columns": schema.names,
                            "types": {field.name: str(field.type) for field in schema},
                            "rows": pq.ParquetFile(path).metadata.num_rows,
                            "metadata": summary,
                        }
                    )
                )
            elif summary["invalid_language_rows"] or summary["invalid_entity_rows"]:
                errors.append(
                    f"file={index}/{len(paths)} name={path.name} invalid_language_rows={summary['invalid_language_rows']} invalid_entity_rows={summary['invalid_entity_rows']}"
                )
            plans.append((path, schema, lc, ec))
        if inspect:
            return []
        if errors:
            raise ValueError(
                "Unsupported terminology metadata: "
                + "; ".join(errors)
                + ". Run --inspect for canonical language/entity metadata; use explicit --language/--entity only when the file's meaning is known. No terminology has been registered."
            )
        collected = {}
        systems = {}
        fragments = Path(tempfile.mkdtemp(prefix=".fragments-", dir=temporary))
        for index, (path, schema, lc, ec) in enumerate(plans, 1):
            logging.getLogger("temu.import").info(
                "terminology_import file=%s/%s stage=READING", index, len(paths)
            )
            term = named_column(schema.names, term_column, TERM_COLUMNS)
            code = named_column(schema.names, code_column, CODE_COLUMNS)
            lower = {name.lower(): name for name in schema.names}
            sab = lower.get("sab")
            sab_code = lower.get("sab_code") or lower.get("code_sab")
            extra = [sab, sab_code] if sab and sab_code and code == lower.get("code") else []
            columns = list(
                dict.fromkeys([term, code, *([lc] if lc else []), *([ec] if ec else []), *extra])
            )
            frame = pd.read_parquet(path, columns=columns, dtype_backend="pyarrow")
            frame = frame.dropna(subset=[term, code])
            frame = classify_metadata(
                frame, relative_path(path), language, entity, lc, ec, language_source
            )
            for (lang, category), part in frame.groupby(["_language", "_entity"], sort=True):
                prepared = prepare_pairs(part, term, code, list_pairing, *(extra or [None, None]))
                system = code_system or ("UMLS" if category == "MEDICATION" and extra else None)
                previous = systems.setdefault((lang, category), system)
                if previous != system:
                    raise ValueError(
                        "Conflicting code systems in one terminology group; import them separately"
                    )
                if prepared.empty:
                    raise ValueError("No valid terminology pairs in group")
                # Spill groups to private temporary Parquet so all languages need
                # not remain as expanded Python strings in memory at once.
                fragment = fragments / f"fragment-{sum(len(v) for v in collected.values())}.parquet"
                prepared.to_parquet(fragment, index=False)
                collected.setdefault((lang, category), []).append(fragment)
                logging.getLogger("temu.import").info(
                    "terminology_import language=%s entity=%s stage=PREPARED pairs=%s",
                    lang,
                    category,
                    len(prepared),
                )
        old = root / "manifest.json"
        registered = (
            {
                (row["language"], row["entity"]): row
                for row in json.loads(old.read_text())["resources"]
            }
            if old.is_file()
            else {}
        )
        for (lang, category), parts in sorted(collected.items()):
            frame = deduplicate_pairs(
                pd.concat([pd.read_parquet(path) for path in parts], ignore_index=True)
            )
            if "references" in frame.columns:
                references = frame.groupby("code", sort=False)["references"].agg(
                    merge_reference_values
                )
                frame["references"] = frame["code"].map(references)
            frame["_match_key"] = frame["term"].map(normalized_form)
            frame = frame.sort_values(["_match_key", "code", "term"], kind="stable").reset_index(
                drop=True
            )
            target_directory = root / ".prepared" / lang
            target_directory.mkdir(parents=True, exist_ok=True)
            staged = temporary / (lang + "-" + category + ".parquet")
            frame.to_parquet(staged, index=False)
            digest = file_sha256(staged)
            # Content-addressed filenames preserve earlier admitted-job contracts.
            target = target_directory / (category + "-" + digest + ".parquet")
            staged.replace(target)
            registered[lang, category] = {
                "language": lang,
                "entity": category,
                "path": str(target.relative_to(root)),
                "sha256": digest,
                "rows": len(frame),
                "concepts": int(frame["code"].nunique()),
                "normalized_forms": int(frame["_match_key"].nunique()),
                "lexical_key_format": KEY_FORMAT,
                "lexical_key_unicode": unicodedata.unidata_version,
                "code_system": systems[lang, category],
            }
        manifest = temporary / "manifest.json"
        manifest.write_text(
            json.dumps({"version": 1, "resources": list(registered.values())}, indent=2),
            encoding="utf-8",
        )
        manifest.replace(old)
        return list(registered.values())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--language")
    parser.add_argument(
        "--language-source",
        choices=("auto", "path", "column"),
        default="auto",
        help="auto prefers an unambiguous path language; column may describe the untranslated source ontology",
    )
    parser.add_argument("--entity", choices=CATEGORIES)
    parser.add_argument("--term-column")
    parser.add_argument("--code-column")
    parser.add_argument("--language-column")
    parser.add_argument("--entity-column")
    parser.add_argument("--code-system")
    parser.add_argument(
        "--list-pairing",
        choices=("aligned", "all"),
        help="Only needed when both term and code contain multiple values; choose their documented relationship explicitly",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Show only column names/counts, never terminology rows",
    )
    args = vars(parser.parse_args(argv))
    os.umask(0o077)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("temu.import").setLevel(logging.INFO)
    settings = Settings()
    result = import_sources(settings=settings, **args)
    if not args["inspect"]:
        print(
            json.dumps(
                {
                    "registered_resources": len(result),
                    "languages": sorted({row["language"] for row in result}),
                    "directory": str(settings.normalization_gazetteer_dir.resolve()),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
