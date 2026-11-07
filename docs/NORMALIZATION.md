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
Existing jobs are unchanged. The default is fast lexical matching; see the 0.9 section below.
Missing terminology or a failing explicitly selected encoder is logged
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
L2-normalized vectors, exact **FlatIP**, and **max_length=256**. In bi-encoder mode, missing native
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
The first **explicit bi-encoder** job for a large dictionary may take substantial time and disk space.

Docker mounts `./gazetteers:/gazetteers:ro`, with the private cache on the shared
`ner-data` volume. Native deployment defaults directly to `./gazetteers` and
`STORAGE_ROOT/normalization-cache`. Restart web and worker after importing or
changing configuration; resubmit queued jobs whose terminology snapshot changed.

For Docker, the service runs as UID 10001. Grant that UID read/search access to
the private directory using filesystem ACLs, for example
`setfacl -Rm u:10001:rX gazetteers`, rather than making confidential files public.


## Fast Parquet matching and corrected language grouping (0.9)

Concept normalization remains optional. When enabled, the default is
`normalization_method=levenshtein`, `normalization_threshold=0.8`. The form also
provides exact matching. **Use bi-encoder (slower)** is a separate, initially
unchecked option; only checking it (API: `normalization_method=bi_encoder`)
loads a normalization Transformer or fits/loads a FAISS index. A miss at the
chosen lexical threshold is a valid unnormalized mention, not a failed model.
NER results and original offsets are preserved.

### Correcting the supplied DT4H archive

The confirmed structure is `dt4h_gazs/parquet/{cs,en,es,it,nl,ro,sv}/` with four
entity Parquet files in each directory. Several translated files retain Spanish
or English ontology language metadata. Version 0.8.2 grouped by that column and
therefore merged seven translations into four resources. For example, its
1,524,350 procedure rows combined languages; that count was not a count of unique
clinical concepts.

The import now prefers an **unambiguous language in the relative directory/file
path**, falling back to the canonicalized language column when absent. Explicit
`--language` overrides both. `--language-source path` requires a path language;
`--language-source column` deliberately restores column-driven grouping for
other datasets. `--inspect` reports the selected policy, path language and
canonical column languages without printing terms or codes.

Stop the old worker and web process, then run in your existing Conda environment
from the repository root:

```bash
git pull --ff-only
python3 -m pip install rapidfuzz==3.14.6
python3 -m scripts.import_gazetteers gazetteers/dt4h_gazs.zip --language-source path
python3 -m scripts.check_config --expect-origin http://127.0.0.1:8000
```

The import should report **28 registered resources** in
`cs, en, es, it, nl, ro, sv` for this archive. Restart both processes with their
shared `.env` (no new environment exports are required):

```bash
# Terminal 1, same Conda environment/repository:
python3 -m uvicorn app.asgi:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
# Terminal 2, same Conda environment/repository:
python3 -m app.worker
```

Submit a **new** job. A completed job is not rewritten, and an already admitted
job whose resource snapshot changed must be resubmitted. Previously queued jobs
without a normalization method default to lexical matching when their pinned
terminology still matches. Old result records remain readable as bi-encoder
results. Old prepared dictionaries/FAISS caches are not removed during import;
do not manually delete prepared files while admitted jobs refer to them.

### Matching, memory and scores

Terminology stays in confidential, content-addressed **Parquet** under
`gazetteers/.prepared/`. There is **no terminology database**. Import deduplicates
term/code pairs, merges medication source identifiers per primary CUI, and writes
sorted `_match_key` strings plus a key-format/Unicode version. These keys use
Unicode NFKC, case folding and whitespace collapsing; mention text/offsets are
never rewritten. Statistics distinguish term/code **pairs**, normalized surface
forms and unique primary concepts. Synonyms legitimately make pairs exceed
concepts even after languages are separated.

The worker reads selected columns with PyArrow, memory mapping enabled, then
uses binary search on sorted keys. Parquet decompression still allocates RAM;
memory mapping is not a claim of zero-copy decompression. Older Parquets without
compatible keys are normalized/sorted in memory. Per-job matcher instances are
reused across document batches and released at job completion; mention lookup
results have a bounded 4,096-query in-memory cache. No mentions/query embeddings
are written to a normalization cache. Four entity categories can occupy RAM at
once; large dictionaries still require memory proportional to selected data.

Levenshtein is exact-first: an exact normalized form returns its matching codes
without scanning fuzzy alternatives. Otherwise the worker searches distinct
forms with RapidFuzz's native unit-cost edit distance, safely prunes impossible
lengths, and ranks unique primary codes by
`similarity = 1 - distance / max(len(query), len(term))`. The threshold is
**inclusive**, adjustable from 0 to 1 (default 0.8). Equal scores sort by code,
then term. Exact ambiguities remain ranked alternatives. Accents are preserved;
this is lexical similarity, not semantic equivalence or a probability. There
is no approximate candidate shortlist that silently drops a better match.
Previously seen queries are reused in RAM. Many distinct unmatched mentions can
still be slower than exact matching.

Exact mode uses only normalized equality and does not use the adjustable fuzzy
threshold. Bi-encoder mode likewise does not interpret that value as a cosine
cutoff. Each annotation records its method, applicable threshold and score kind;
lexical annotations have no encoder/max-length value. Lexical mode requires no
encoder configuration and prefers the native-language dictionary, with English
fallback only when that dictionary is unavailable. Fallback searches the
original mention; it does not translate it.

Bi-encoder opt-in keeps native `TransformerFaissRetriever.fit_faiss` and
`get_candidates`, CPU exact FlatIP, length 256, Spanish HERBERT-P and published
DT4H parents priorities. The private index cache still holds at most three
languages with 72-hour idle expiry. The loaded index is reused across document
batches when the same category remains active. Its first cold build encodes every vocabulary term/code row, so large
synonym sets can take considerable time. It is never triggered by lexical mode.

See [verification and synthetic measurements](VERIFICATION.md) for the measured
scope and limitations. Lexical matching does not require re-installing a CPU
Torch profile over an existing Conda GPU installation; install RapidFuzz only if
all other inference dependencies are already present. Docker uses the updated
CPU/GPU lock files.


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
silently rewritten. When bi-encoder mode is explicitly selected, its first use creates an index on demand; later compatible
jobs reuse it. No additional pip dependencies were introduced for this fix.


## Mixed ISO/UMLS language metadata (0.8.2)

Terminology language values are canonicalized before grouping. UMLS LAT and
ISO 639-2 values such as SPA, ENG, CZE/CES, DUT/NLD, ITA, RUM/RON and SWE map to
es, en, cs, nl, it, ro and sv. Whitespace, recognized language names, regional
forms such as es-ES and single-language list cells are supported. Several aliases
of one language may share a cell; several different languages remain ambiguous.
Explicit --language/--entity overrides are canonicalized in the same way.

The importer checks language/entity metadata in **all files before preparing any
terminology group**. Unknown or ambiguous metadata remains an error, with the
file position/name and separate invalid-language/entity row counts. Existing
registered resources are preserved on a failed attempt. No vocabulary values are
included in these diagnostics. `--inspect` now includes canonical language/entity
metadata and invalid row counts, even when inference from the filename is
ambiguous. It still does not import dictionaries.

After updating, retry the original ZIP command without changing its location:

```sh
git pull --ff-only
python3 -m scripts.import_gazetteers gazetteers/dt4h_gazs.zip
```

If metadata remains unsupported, `python3 -m scripts.import_gazetteers
gazetteers/dt4h_gazs.zip --inspect` identifies the affected file and field without
printing terminology. No new dependencies are required.
