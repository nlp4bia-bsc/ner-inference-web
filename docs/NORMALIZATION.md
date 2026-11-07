# Private terminology and concept normalization

Place the confidential files **inside `gazetteers/` at the repository root** on
both the web and worker host (the same checkout in a native deployment). This
entire directory, all Parquet files and all FAISS files are ignored by Git.
It is never a static-file route, a package resource or part of a Docker build.
`storage/normalization-cache/` is also ignored. Keep local backups private.

From the repository root, in the active **Conda** environment:

```bash
mkdir -p gazetteers
chmod 700 gazetteers
# Copy dt4h_gazs.zip here using your normal private file-transfer method.
python3 -m scripts.import_gazetteers gazetteers/dt4h_gazs.zip --inspect
python3 -m scripts.import_gazetteers gazetteers/dt4h_gazs.zip
# Check privacy before any commit:
git check-ignore gazetteers/dt4h_gazs.zip gazetteers/manifest.json
```

The import is local and never uploads dictionaries. The tool reads common
term/code, language and entity columns or infers the language/category from
paths. If ambiguous, import individual files with explicit flags:

```bash
python3 -m scripts.import_gazetteers gazetteers/raw/es-disease.parquet \
  --language es --entity DISEASE --term-column term --code-column code \
  --code-system SNOMEDCT
```

Supported categories: MEDICATION, PROCEDURE, DISEASE, SYMPTOM. `--inspect`
prints column names, Arrow types and row counts, without vocabulary values.
The supplied metadata confirms `code`, `language`, `term`, `semantic_tag` and
`mainterm` in the disease/procedure/symptom tables, and medication tables with
`code`, `language`, `term`, `SAB` and either `SAB_code` or `code_SAB`. The binary
archive itself has not been retrieved in this execution. Use explicit flags if
a different schema does not match. Imports reject unsafe ZIP paths/symlinks/
encryption and atomically update the private manifest. Expanded intermediate
groups spill to private temporary Parquet rather than retaining every language's
expanded Python strings together. CLI progress reports file/group counts only.
Content-addressed prepared files preserve the terminology admitted with a job;
stop/drain jobs before manually removing old prepared versions.

Enable **Concept normalization** when submitting a job (API: `normalize=true`).
Existing jobs are unchanged. Missing terminology or a failing encoder is logged
without patient text, leaves that category unnormalized, and preserves the NER
results as partial results. Similarity is a retrieval score, not a probability
or an automatically verified clinical decision. The inspector shows the concept,
ranked alternatives, score, encoder and fallback language. TSV carries a JSON
`normalization` field; BRAT keeps original T offsets and adds N reference lines.

The public configuration in `catalog/normalization.yaml` contains **model IDs
only**: Spanish ICB-UMA/HERBERT-P (native mean pooling); other published DT4H
CardioBERTa **parents** models (CLS pooling), prioritizing enriched, then
only_snomed, then translations_only when published. Models load on demand through
the normal Hugging Face cache. Native `ner_lab` TransformerFaissRetriever uses
L2-normalized vectors, exact **FlatIP**, and **max_length=256**. Missing native
terminology/encoder configuration selects the English terminology. This searches
the original mention against English entries; it does not translate the mention.

Indices and vocabulary are private in `storage/normalization-cache/<lang>/`.
Only terminology vectors are persisted, never patient mention/query vectors.
The cache holds at most **three languages**, evicts least recently used languages,
and removes idle languages after **72 hours**. Cleanup runs with the worker;
startup/reuse also prunes. Each index records hashes of its dictionary, model
revision and runtime contract, checks file integrity, and rebuilds if that
contract changes. The limit/TTL may be lowered but cannot exceed 3/72.
The three-language limit applies to FAISS indices, not downloaded HF checkpoints.
The first job for a large dictionary may take substantial time and disk space.

Docker mounts `./gazetteers:/gazetteers:ro`, with the private cache on the shared
`ner-data` volume. Native deployment defaults directly to `./gazetteers` and
`STORAGE_ROOT/normalization-cache`. Restart web and worker after importing or
changing configuration; resubmit queued jobs whose terminology snapshot changed.

For Docker, the service runs as UID 10001. Grant that UID read/search access to
the private directory using filesystem ACLs, for example
`setfacl -Rm u:10001:rX gazetteers`, rather than making confidential files public.


## Importing the DT4H ZIP after updating to 0.8.1

The ZIP belongs exactly at `gazetteers/dt4h_gazs.zip`. Copying it there or running
`--inspect` does not register terminology. The worker's old
`NormalizationUnavailable` at the initial catalog lookup meant no usable imported
resource was found; no encoder or FAISS index had run at that point.

From the same Conda environment and repository root, after `git pull --ff-only`:

```bash
python3 -m scripts.import_gazetteers gazetteers/dt4h_gazs.zip
python3 -m scripts.check_config --expect-origin http://127.0.0.1:8000
```

The import now expands a list of synonyms with one code, or one term with a list
of codes. Arrow/Python/NumPy lists and serialized JSON/Python lists are accepted.
Duplicates and empty entries are handled without losing positional alignment.
If **both** term and code contain several values, the default rejects an ambiguous
mapping. Use `--list-pairing aligned` only when positions correspond, or
`--list-pairing all` only when every term names every code in that row. These are
explicit data-interpretation choices, not generic ways to bypass import errors.
Nested records still require preprocessing. No default Cartesian association is
created for ambiguous rows.

For medications, `code` remains the primary **UMLS CUI**. `SAB` identifies the
source terminology, and `SAB_code`/`code_SAB` its identifier. The importer preserves
these source references and infers UMLS as the medication code system when those
columns are present. Duplicate term/CUI rows merge their source references.
Several primary CUIs in a row with source identifiers require preprocessing so
source IDs cannot be attached to the wrong CUI. The encoder still retrieves by
term/primary code. Additional references survive warm FAISS reuse, appear in the
inspector and JSON/TSV, and produce separate BRAT N records for the same T span.
They never create duplicate mentions or change character offsets.

`check_config` now has a `normalization` report: private directory, manifest,
registered resources, file presence and reasons for unavailable categories. It
does not import NLP, read dictionary terms or create files. Worker logs and model
cards distinguish unimported dictionaries, missing files, missing category or
encoder configuration, and disabled normalization. A missing native-language
file can fall back to a valid English resource.

Restart web and worker together after updating/importing, then submit a **new**
annotation job with normalization enabled. Completed partial jobs are not
silently rewritten. The first use creates its index on demand; later compatible
jobs reuse it. No additional pip dependencies were introduced for this fix.
