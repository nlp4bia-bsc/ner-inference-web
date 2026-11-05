# TEMU multilingual NER

A minimal, account-free FastAPI application for uploading UTF-8 TXT/ZIP corpora,
queuing multilingual NER, and downloading BRAT/TSV annotations. NLP comes from
[BSC ner_lab](https://github.com/nlp4bia-bsc/ner_lab), pinned to commit
`8640d4797b081a5f6b66d9b45c11269542a79a26`.

**No checkpoints are supplied.** The initial catalog is deliberately unavailable;
the UI and server reject inference until an administrator validates a local model.
There is no production mock mode and no automatic model download.

## Local start (Linux, Python 3.12 recommended; Python >=3.11)

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install -e '.[test]'
cp .env.example .env
uvicorn app.asgi:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

In another terminal, using the same environment and working directory:

```sh
. .venv/bin/activate
python -m app.worker
```

Open http://localhost:8000. The web server serves the catalog without the NLP extra.
The worker remains idle without models. `/health` checks HTTP liveness; `/ready`
checks the database/worker heartbeat and reports whether models are available.

For **real inference**, install the pinned NLP dependencies before preflight:

```sh
pip install -r requirements-nlp.lock
python -m scripts.validate_models
```

The upstream NER extra includes training/search dependencies and Torch/CUDA wheels;
it is large. CPU installations can first install `torch==2.10.0` from the PyTorch
CPU index, then install the extra. See deployment notes before changing the lock.

## Configuration and adding models

Edit `catalog/models.yaml` (overridable using `MODEL_CONFIG_PATH`):

```yaml
languages:
  es:
    display_name: Spanish
    statistics_model: null  # first selected checkpoint tokenizer is the reference
    entities:
      DISEASE:
        display_name: Diseases
        description: Disease mentions
        model_id: es-disease-v1
        version: "1"
        model_dir: /models/es-disease
        enabled: true
        min_score: 0.5
        batch_size: 16
```

1. Provision a trusted, complete local checkpoint and its fast tokenizer.
2. Set its language, entity, path, model ID and version in YAML.
3. Run `python -m scripts.validate_models` with the production paths/environment.
   This loads weights and reconstructs the saved encoder offline, then creates a
   private validation receipt. Missing/incompatible checkpoints fail preflight.
4. Restart API and worker together. Do not replace checkpoints while jobs are pending.

No frontend changes are needed. `encoding.json` must match the language and target
label. The checkpoint digest must match its validation receipt at startup and execution.

The catalog lives in `catalog/` because this development workspace provisioned
`config/models.yaml` as a root-owned directory, rather than a writable file. On
BSC the path can instead be `/etc/temu/models.yaml` via `MODEL_CONFIG_PATH`.

## Docker

```sh
cp .env.example .env
docker compose up --build -d
```

This starts the usable web/catalog/queue service without NLP packages. For actual
inference after provisioning models and receipts:

```sh
INSTALL_NLP=true docker compose build web
# Preflight must see the same /models paths as the running services.
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/catalog:/service/catalog:rw" worker python -m scripts.validate_models
docker compose up -d --force-recreate
```

Use a private named data volume on a local filesystem and one worker. The API is
bound to localhost for a trusted HTTPS reverse proxy. See
[deployment](docs/DEPLOYMENT.md) for proxy/IP handling, TLS, subpaths, resources,
CA secrets in managed build environments, and retention operations.

## Tests

```sh
python -m pytest -q
python -m ruff check app scripts tests
python -m ruff format --check app scripts tests
```

`tests/test_statistics_real.py` and the pipeline integration use real `lab.core`
with a synthetic local tokenizer and skip explicitly if `lab` is absent. Browser
tests require Playwright and Chromium, plus a running local server:

```sh
pip install playwright
BROWSER_TESTS=1 python -m pytest -q tests/test_browser.py
```

Browser tests use catalog HTTP fixtures; controlled prediction fixtures exist only
in tests. They are not biomedical model results. See [verification](docs/VERIFICATION.md)
for actual run results and remaining infrastructure checks.

## Layout

```text
app/
  asgi.py, main.py       HTTP API, admission bounds and HTML views
  config.py, db.py       configuration, SQLite FIFO/state/rate limiting
  storage.py, worker.py  private storage and supervised sequential inference
  services/
    registry.py         checkpoint catalog, digest and compatibility checks
    documents.py        safe bounded TXT/ZIP ingestion
    inference.py        real ner_lab adapter and validated span merge
    statistics.py       native ner_lab corpus and document statistics
    export.py           BRAT/TSV/JSON and deterministic packaging
    cleanup.py          retention, tombstones and orphan cleanup
  templates/, static/   English responsive UI and lightweight polling
catalog/models.yaml     disabled example language/entity catalog
scripts/                administrator preflight and cleanup entry points
tests/                  unit, API, pipeline, statistics and Chromium checks
docs/                   architecture, API, integration, operations and security
Dockerfile, docker-compose.yml, .env.example, requirements*.lock
```

## Outputs

`filename` always means the original relative path **including `.txt`**.
The archive contains `brat/documents/<original path>.txt` and its matching `.ann`,
`brat/annotation.conf`, `annotations.tsv`, `document_statistics.tsv`,
`statistics.json`, and `manifest.json`. Every document has an ANN, even when empty.

For input `patient.txt` with text `Cancer.` a controlled example is:

```text
T1	DISEASE 0 6	Cancer
```

TSV begins with the canonical five columns, then real confidence and metadata:

```tsv
filename	label	start_span	end_span	text	score	language	model_id	submitter_name	submitter_email
patient.txt	DISEASE	0	6	Cancer	0.9	en	example-model	Researcher	user@example.org
```

These examples explain the format; they are not actual checkpoint predictions.
Results expire 24 hours after completion; failed jobs are also cleaned after 24
hours. The worker and API sweep independently. Expired metadata is scrubbed and a
minimal tombstone remains for another 24 hours. A manual sweep is available via
`python -m scripts.cleanup`.

## Technical decisions and limitations

SQLite WAL replaces PostgreSQL/Redis/RQ for this single-host first version. Atomic
transactions keep admission, FIFO state and rate limiting in one source of truth;
a lifetime `flock` enforces exactly one supervising worker. No distributed queue
reconciliation is required. This design requires a local filesystem, Linux and a
single host; multi-host processing needs a database/queue migration.

Whole jobs succeed or fail. Invalid offsets or model/statistics/export failures
produce no downloadable partial result. Progress is a genuine terminal document
count, never an estimated percentage. The first selected checkpoint provides a
reference tokenizer unless a local statistics tokenizer is configured.

Production still needs BSC-provided checkpoints, validation against real corpora,
HTTPS/domain/proxy configuration, storage/backups/privacy policy, capacity/GPU
sizing and monitoring. No precision/recall/F1 is generated without gold annotations.
No registration, email delivery, language detection, ensemble UI or BRAT editor is
implemented. The storage protocol is an extension seam; S3/MinIO is not implemented.

Further documentation: [architecture](docs/ARCHITECTURE.md),
[ner_lab integration](docs/NER_LAB_INTEGRATION.md), [API](docs/API.md),
[model registry](docs/MODEL_REGISTRY.md), [security](docs/SECURITY.md).
