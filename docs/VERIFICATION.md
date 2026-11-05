# Latest: phase 2 verification

- Baseline before edits: **71 passed in 22.57s**.
- First backend refactor: **69 passed** excluding the then opt-in browser cases.
- Final full run: `SCREENSHOT_OUTPUT=work/screenshots BROWSER_TESTS=1 work/locked-env/bin/python -m pytest -q`: **94 passed in 48.16s**, no skips.
- Ruff lint/format and Prettier checks passed; `git diff --check` passed.
- Viewer/home tests used self-started temporary `/ner` servers and real document
  APIs, at 320/375/390/768/1024/1440/1920/2560px. They selected every nested,
  crossing and equal-boundary annotation, including four simultaneous spans;
  checked actual selected fragments, filters, original Unicode text, emoji search,
  model/confidence, keyboard interaction, empty predictions and horizontal overflow.
- API tests checked 1,000 indexed documents, paginated metadata (no full-text bulk
  response), fragment-crossing spans, whole-document search, v1 index backfill,
  prefixed OpenAPI/routes/static links, origin/body limits and exact 72-hour denial
  on every old/new private endpoint. Cleanup was idempotent and removed originals,
  outputs and viewer indexes; long queue waiting did not consume retention time.
- Existing actual ner_lab tiny-BERT CPU inference and native statistics tests ran
  again; no scientific NER logic was reimplemented or production mock enabled.
- Default non-NLP Docker image built; Compose web/worker startup and health/ready
  returned 200. A separate image instance with APP_PREFIX=/ner served prefixed
  home/health/static viewer JS/languages successfully. Production TLS/GPU and the
  large NLP-enabled Docker image remain untested as previously documented.
- [Screenshots](PREVIEWS.md) record desktop/mobile synthetic test states.

No claim of BSC deployment, clinical accuracy, formal WCAG certification or maximum
annotation-density performance is made. The requested Hugging Face/BRAT web pages
were blocked by network policy; the official BRAT GitHub source was inspected.
See VISUALIZATION_ARCHITECTURE.md for exact references and the custom-renderer decision.

---

# Historical phase 1 verification

Executed in the managed Linux workspace on 2026-11-05 (Python 3.12.14).

- `BROWSER_TESTS=1 work/locked-env/bin/python -m pytest -q`: **71 passed**, no skips,
  in 22.61 seconds. HTTP dependencies in that environment came from requirements.lock.
- Without browser opt-in, the two Chromium cases are explicitly skipped.
- `python -m ruff check app scripts tests`: passed.
- `python -m ruff format --check app scripts tests`: passed.
- `git diff --check`: passed.
- Docker image built successfully using a CA secret and non-root runtime.
- `docker compose config --quiet`: passed; web + worker started successfully.
- Compose `/health`: HTTP 200; `/ready`: HTTP 200,
  `{ "status": "ready", "models_available": false }` with the disabled example catalog.

Coverage includes individual/multiple TXT, nested ZIP folders, original CRLF/Unicode,
1,000 accepted vs 1,001 rejected documents, empties/invalid UTF-8/binary/unsupported
files, traversal/duplicate/link ZIP entries, compression bombs and byte/count bounds;
metadata/catalog validation, disabled entities and spoofed forwarding headers;
atomic concurrent rate limiting and claims, FIFO/restart/retry exhaustion, capacity,
retention and deletion; token hashing/404/409/410, downloads/statistics; deterministic
deduplication, overlap preservation, invalid offsets and BRAT/TSV round trips.
Chromium exercised dynamic language/entity updates, unavailable entities, multiple
selection, execution gating and horizontal overflow at 390px and 1366px.

`lab.core` statistics were executed with a locally built synthetic tokenizer;
per-document/native aggregate counts matched. The HTTP/queue/export integration
also used controlled predictions injected only by tests.

A separate full integration generated a tiny random BERT checkpoint locally,
called the actual offline administrator preflight, submitted through the real API,
started the actual supervised worker, executed `lab.ner.predict_entities` on CPU,
computed native statistics, downloaded BRAT/TSV, and verified a second worker was
rejected by its lock. No external pretrained checkpoint was downloaded. This tests
mechanics/offset integrity, **not clinical accuracy** or biomedical model quality.

NLP test runtime: ner_lab commit 8640d4797b081a5f6b66d9b45c11269542a79a26,
Torch 2.10.0+cpu, Transformers 5.22.1, datasets 5.1.0, accelerate 1.15.0,
pandas 2.2.3, pyarrow 26.0.1. The complete GPU/training dependency set in
requirements-nlp.lock was resolved but its large INSTALL_NLP=true Docker build
was not executed. The default no-NLP image and Compose service pair were built/run.

Still pending: BSC real checkpoints/corpora, clinical accuracy, maximum-corpus/model
capacity and soak tests, GPU runtime, real trusted proxy/TLS/domain integration,
backup/retention policies and production monitoring. No real institution model is
marked available by these tests. The checked-in catalog contains no functioning
model paths or synthetic models.

## Follow-up review of the resubmitted requirements

The second uploaded specification is byte-for-byte identical to the original
(SHA-256 `6d3624cc7af3b958a5086cb44b544600515d04759d274cf8e38be0e63af8a115`).
The follow-up review corrected two operational issues without changing the NLP
contract or adding fake production models:

- Completed/failed jobs now count against the storage budget by their actual
  retained bytes, instead of keeping a worst-case active-job reservation for the
  entire retention period. Free-space checks include queued-job reservations.
- Worker result transfer now uses a private, atomically published JSON file.
  A result larger than an OS pipe buffer cannot deadlock the supervisor while it
  waits for child exit. Timeout enforcement covers shutdown after publication;
  an earlier attempt's result file cannot make a failed retry appear successful.

Five additional regression cases exercise these behaviors using real spawned
processes (including a 1 MiB summary and a child that stalls after publication).
The complete 71-case suite also reran browser checks, real ner_lab statistics and
the actual CPU inference/worker integration with a synthetic checkpoint. Ruff,
formatting, Docker image build and Compose startup were checked again.
