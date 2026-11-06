"""Import confidential local Parquet dictionaries; contents never enter Git or logs."""

import argparse
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from app.config import Settings
from app.services.normalization_catalog import CATEGORIES, file_sha256

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
LANGUAGE_NAMES = {
    "spanish": "es",
    "english": "en",
    "catalan": "ca",
    "czech": "cs",
    "dutch": "nl",
    "romanian": "ro",
    "swedish": "sv",
    "italian": "it",
    "greek": "el",
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
        LANGUAGE_NAMES.get(token, token)
        for token in tokens
        if token in LANGUAGE_NAMES
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
        collected = {}
        for path in paths:
            schema = pq.read_schema(path)
            if inspect:
                print(
                    json.dumps(
                        {
                            "file": path.name,
                            "columns": schema.names,
                            "rows": pq.ParquetFile(path).metadata.num_rows,
                        }
                    )
                )
                continue
            term = named_column(schema.names, term_column, TERM_COLUMNS)
            code = named_column(schema.names, code_column, CODE_COLUMNS)
            lower = {name.lower(): name for name in schema.names}
            lc = language_column or next(
                (lower[key] for key in ("language", "lang") if key in lower), None
            )
            ec = entity_column or next(
                (
                    lower[key]
                    for key in ("entity", "entity_type", "category", "semantic_group")
                    if key in lower
                ),
                None,
            )
            columns = list(
                dict.fromkeys([term, code, *([lc] if lc else []), *([ec] if ec else [])])
            )
            frame = pd.read_parquet(path, columns=columns, dtype_backend="pyarrow")
            frame = frame.dropna(subset=[term, code])
            frame["_language"] = (
                str(language)
                if language
                else frame[lc].astype(str).str.lower()
                if lc
                else guess_language(
                    path.relative_to(temporary)
                    if path.is_relative_to(temporary)
                    else path.relative_to(Path(source).resolve())
                    if Path(source).is_dir()
                    else path.name
                )
            )
            if entity:
                frame["_entity"] = entity
            elif ec:
                frame["_entity"] = (
                    frame[ec]
                    .astype(str)
                    .map(lambda value: ENTITY_NAMES.get(value.lower(), value.upper()))
                )
            else:
                frame["_entity"] = guess_entity(
                    path.relative_to(temporary)
                    if path.is_relative_to(temporary)
                    else path.relative_to(Path(source).resolve())
                    if Path(source).is_dir()
                    else path.name
                )
            for (lang, category), part in frame.groupby(["_language", "_entity"], sort=True):
                if not re.fullmatch(r"[a-z]{2}", lang) or category not in CATEGORIES:
                    raise ValueError(
                        "Unsupported terminology language/entity group; provide explicit mapping"
                    )
                prepared = part[[term, code]].rename(columns={term: "term", code: "code"}).copy()
                prepared["term"] = prepared["term"].astype(str).str.strip()
                prepared["code"] = prepared["code"].astype(str).str.strip()
                if (
                    prepared["term"].str.startswith("[").any()
                    or prepared["code"].str.startswith("[").any()
                ):
                    raise ValueError(
                        "List-valued term/code columns need explicit flattening before import"
                    )
                prepared = prepared[
                    (prepared["term"] != "") & prepared["code"].str.fullmatch(r"[A-Za-z0-9_.:/-]+")
                ]
                if prepared.empty:
                    raise ValueError("No valid terminology pairs in group")
                collected.setdefault((lang, category), []).append(prepared)
        if inspect:
            return []
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
            frame = (
                pd.concat(parts, ignore_index=True)
                .drop_duplicates(["term", "code"])
                .reset_index(drop=True)
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
                "code_system": code_system,
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
    parser.add_argument("--entity", choices=CATEGORIES)
    parser.add_argument("--term-column")
    parser.add_argument("--code-column")
    parser.add_argument("--language-column")
    parser.add_argument("--entity-column")
    parser.add_argument("--code-system")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Show only column names/counts, never terminology rows",
    )
    args = vars(parser.parse_args(argv))
    os.umask(0o077)
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
