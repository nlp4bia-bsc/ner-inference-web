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
prints column names and row counts, without vocabulary values. This environment
could retrieve Drive metadata but could not download the 81 MB archive; its real
column names remain unverified. Use the explicit flags if automatic detection
does not match your files. Imports reject unsafe ZIP paths/symlinks/encryption,
normalize to term/code Parquet and atomically update the private manifest.
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
