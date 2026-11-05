# Latest: V5 institutional interface (0.5.0)

Baseline 967e87d, with 40 phase-one security/migration/browser cases passed before
redesign (46.03s). Final complete regression: **188 passed in 305.86s**, no
failures/skips. Clean HTTP-only: **132 passed, 56 skipped in 41.24s**, with one
compatible Starlette/httpx deprecation warning. Full execution includes browsers
and native random tiny-BERT CPU integration; it does not assert clinical accuracy.

The eight-resolution/two-prefix matrix covers the new institutional screens and
real account flows, model selection, overlap/keyboard interactions, admin/MFA,
confirmation/cancellation and revocation. Axe-core 4.14.0 ran 60 EN/ES/CA scans with
zero automatic WCAG-tagged violations; incomplete contrast checks are disclosed.
Ruff, Jinja/static format, Bandit medium/high, HTTP dependency audit, wheel/sdist
and no-NLP Docker pass. Runtime root/prefix checks preserve private401/303 gates
and complete real prefix registration/captured mail/verification/login/logout.

See [REDESIGN_VERIFICATION.md](REDESIGN_VERIFICATION.md) for the13-part delivery,
captures, commands, measurements and remaining limits; [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)
and [USER_EXPERIENCE.md](USER_EXPERIENCE.md) for maintained frontend contracts.
No new schema migration or scientific consolidation/offset change was introduced.
The earlier Torch, SMTP, TLS/BSC, legal-review and clinical/GPU limitations remain.

---

# Historical: V4 authentication, ownership and quotas

Baseline: b8d4d4f on branch work, **128 passed in83.68s** before implementation.
Final full regression on Python3.12.14:

```sh
SCREENSHOT_OUTPUT=work/auth-screens BROWSER_TESTS=1 work/locked-env/bin/python -m pytest -q
```

**168 passed in145.76s**, zero failures/skips. This includes actual Chromium
registration, captured email confirmation, login/session/CSRF, two independent
owners and cross-account denials, historical-token aliases, quotas, reset/logout,
admin bootstrap/MFA/recovery-code display and permission changes, and EN/ES/CA
forms under both root and APP_PREFIX=/ner. Cross-tab account switches clear the
previous owner's view. Existing incremental publication, native tiny-BERT CPU,
overlap/viewer/export, admission/recovery and72h retention regressions also pass.
The controlled browser predictor is synthetic; native inference tests separately
exercise ner_lab with random tiny weights, not clinical-model accuracy.

A clean HTTP/test environment without Torch/ner_lab ran **128 passed,40 skipped in
20.65s**. Skips explicitly cover browser opt-in and optional native NLP cases.
One compatible Starlette/httpx deprecation warning remains. The full run above
executes all168 cases, including those integrations. All acceptance scenarios A–H
and their evidence are mapped in [SECURITY_AUDIT_V4.md](SECURITY_AUDIT_V4.md).

Other executed checks:

- Ruff lint and format (89 Python files), Prettier for matching static/legacy
  template files, Jinja compilation regression, and git diff --check pass.
- Bandit app/scripts at medium/high severity: zero unsuppressed findings. The
  narrow reviewed suppressions and independent findings/corrections are documented
  in [SECURITY_REVIEW_V4.md](SECURITY_REVIEW_V4.md) and the audit.
- HTTP pinned dependency audit: zero known advisories. Cryptography was upgraded
  to50.0.2 following audit findings. CPU/GPU lock registry audits retain **two
  upstream Torch advisories**, detailed below; no ignore filter hides them.
- sdist/wheel0.4.0 build successfully. Wheel authentication/admin modules, assets
  and templates were inspected; the source distribution includes the bootstrap
  script. Docker/repository deployments provide python -m scripts.create_admin.
- The existing mechanics benchmark was adapted to actual test registration/login.
  An8-document/32-byte smoke completed with synthetic predictions, including
  incremental publication and exports. This is not a load or clinical benchmark.
- Final no-NLP Docker image built with the session CA secret; Compose configuration
  validates. Web/worker restarted together, remain running and ready. The actual
  pre-upgrade runtime database had **zero jobs**; additive owner/auth tables were
  checked after migration. Populated legacy-copy preservation, FIFO/deadlines,
  rollback-on-DDL-failure and idempotence are verified by migration tests.
- Root and isolated /ner containers return minimal health/readiness200, private
  HTML303 to login, and private APIs/catalog/OpenAPI401. The isolated prefix
  container additionally completed real registration -> captured file mail ->
  confirmation -> login -> dashboard/OpenAPI0.4.0 -> logout -> session401. It was
  removed after verification. Initial prefix readiness503 before its worker
  heartbeat was expected; the repeated smoke after worker startup passed.
- No actual external email was sent. The persistent production-default container
  has no SMTP configuration and safely refuses mail-dependent account actions;
  a real registration probe returned503 without inserting an account. It does not
  auto-verify users. No persistent administrator or test user was
  created there. Unrelated existing database/cache containers and volumes remain.

GitHub Actions now gates auth/security regressions, browser scenarios, Ruff,
Bandit and HTTP dependency auditing. These are local results, not a claim that a
hosted Actions run or a BSC production deployment completed.

## Remaining deployment limits

Both optional neural locks report PYSEC-2026-139 and PYSEC-2025-194 for upstream
Torch2.10.0, required exactly by the pinned ner_lab revision. The latter audit
lists2.13.0 as fixed; the former lists no fixed version. HTTP clients cannot load
checkpoints/JIT/pt2, and runtime checkpoints must be immutable/offline-validated;
these controls do not resolve package advisories. Resolve upstream before calling
the neural production profile hardened. Reports are versioned in [security/](security/).

Real SMTP delivery, institution TLS/HSTS/proxy integration, legal notices, key/
backup/MFA recovery operations, clinical checkpoints/GPU/full neural images and
external load/penetration testing remain unvalidated. SQLite is single-host.
See [deployment](DEPLOYMENT.md), [authentication](AUTHENTICATION_V4.md) and
[recovery](RECOVERY_V4.md). No certification or invulnerability is claimed.

---

# Historical: model catalog correction

Baseline: V3 commit 5f0fb4c, 117 passing tests. Final regression on Python 3.12.14:
`SCREENSHOT_OUTPUT=work/screenshots-catalog BROWSER_TESTS=1 work/locked-env/bin/python -m pytest -q`
completed with **128 passed in 85.38s**, no skips. Ruff lint/format, Prettier and
`git diff --check` passed. The sdist/wheel and non-NLP Docker image built.

New cases verify the 36 Excel repository links and retained legacy IDs, the exact
combined-corpus Greek repository, flat categories, explicit same-category and
multilingual selection, rejection of unknown/duplicate/incompatible checkpoints,
dependency cycles/order and forwarding of upstream annotations, canonical merge
with all original labels/scores and legitimate overlaps, all-model publication,
BRAT/TSV/JSON provenance, changed mappings invalidating snapshots/receipts, legacy
queued-job compatibility, and desktop/mobile provenance display. Browser forms
are tested at all eight existing viewports with no automatic selection, plus an
actual inventory-based catalog fixture and explicit multipart checkpoint IDs.

The native CPU test preflights two records pointing to a tiny random BERT,
executes both using ner_lab, consolidates their spans under a mapped category,
and checks both source IDs survive. This validates mechanics and the new receipt
contract, not the quality of any clinical checkpoint. Existing real inference,
recovery, upload, quota, 72-hour expiry, prefix and overlap regressions also pass.

The imported catalog contains 51 new checkpoint/experiment records plus the three
legacy entries; some checkpoints have several language/category bindings. No
imported checkpoint was downloaded, initialized or enabled. The full clinical
schemas, LocationSubTagger input/dependency contract, custom DT4H MTL architecture,
GPU deployment and exact Greek combined-corpus scores remain unverified. See
MODEL_REGISTRY.md for per-source evidence and the conservative execution guards.

A clean HTTP/test-only environment separately ran **98 passed, 30 skipped in
7.38s** (browser opt-in and real NLP cases skipped explicitly); one compatible
Starlette/httpx deprecation warning remains.

After the coordinated Docker web/worker restart, home, health, readiness, local
API reference, OpenAPI and form JavaScript returned 200. The live catalog exposed
60 language/category bindings for 54 distinct records, zero executable models,
and the exact Greek repository. A separate container checked the same routes under
`APP_PREFIX=/ner`, plus its language-filtered catalog, with an isolated worker.
The first temporary startup failed because accumulated build images filled the
environment disk; removing obsolete images from this project/build cache recovered
2.2 GiB. The repeated prefix smoke passed; no persistent volumes were removed.

---

# Historical: V3 verification

Baseline audited at 9c95bb5: **94 passed in 51.77s** before edits.

Executed locally on Python 3.12.14 / Linux:

- Full native/browser regression: **117 passed in 65.56s**, no skips, with
  `SCREENSHOT_OUTPUT=work/screenshots-v3 BROWSER_TESTS=1 work/locked-env/bin/python -m pytest -q`.
- A separate clean environment with only requirements.lock, test extras and
  Playwright (no Torch/ner_lab) ran **91 passed, 26 explicitly skipped in 4.80s**.
  The skips were browser opt-in cases and optional real NLP integrations.
- That clean environment then ran all selected browser cases with BROWSER_TESTS=1:
  **21 passed in 46.47s**. A Starlette warning about the compatible httpx fallback
  is recorded; no functional failures occurred.
- Ruff lint/format and Prettier checks passed; `git diff --check` passed.
- `uv build --out-dir work/dist` built both the 0.3.0 sdist and wheel; the wheel
  includes the new persistence, publication, document contract and progress modules.
- The final non-NLP Docker image built successfully. After a coordinated Compose
  web/worker restart, `/`, `/health`, `/ready`, `/docs`, `/openapi.json` and
  `/static/progress.js` returned 200. A separate container with `APP_PREFIX=/ner`
  served the same routes under `/ner`; readiness returned 503 with no worker and
  200 after starting its isolated worker. Both schemas reported version 0.3.0 and
  the progress endpoint. `models_available` was false in this deliberate no-NLP
  smoke run. The temporary prefixed container was removed afterward.
- CPU and GPU NLP dependency profiles were resolved separately. Full NLP Docker
  builds, GPU execution and real BSC/clinical checkpoints were not run.
- GitHub Actions now configures lint, unit/light integration, browser, package and
  no-NLP Docker smoke jobs with no private checkpoints. Remote Actions execution
  is not claimed; the corresponding local clean-environment commands were run.

New regressions cover exact pasted Unicode/CRLF bytes and exclusive input modes,
actual body limits without Content-Length, failed-upload cleanup and live staging
ownership; concurrent eight-client HTTP admission/FIFO; no directory traversal in
admission; versioned migration with unchanged old tokens/deadlines; all-model
publication while the job is running; partial failures/attachments; crash before
SQL commit, verified restart reuse, missing-artifact reprocessing and idempotent
counts; storage-budget denial before writes; actual native session/public API
prediction equivalence, warm model reuse and streamed/public statistic equality.

Chromium exercises all existing eight viewports plus paste acceptance dialogs,
collapsible progress, completion notification, server/browser clock skew, a live
expiry that clears text/table/inspector/links, folder navigation, synchronized row
selection, individual downloads and all overlapping-span selections. Controlled
predictors/catalog fixtures are test-only and never presented as clinical results.

Measurements, raw JSON and limits are in PERFORMANCE_V3.md and benchmarks/.
The 1,000x16KiB ingestion fixture reduced peak traced Python allocations from
32.29 to 1.33 MiB; full admission is not claimed faster than the old pure loader.
Real tiny-BERT timings, publication/ZIP/HTTP timings and synthetic renderer timings
are reported separately and are not GPU or clinical throughput predictions.

Known remaining validation: actual biomedical checkpoints/corpora, GPU/driver and
full neural-image deployment, external-user TCP/load/soak tests, institutional data
policy, BSC TLS/domain integration and hosted CI runner results. No clinical
accuracy, formal WCAG certification or BSC production deployment is claimed.

---

# Historical: phase 2 verification

- Baseline before edits: **71 passed in 22.57s**.
- First backend refactor: **69 passed** excluding the then opt-in browser cases.
- Final full run: `BROWSER_TESTS=1 work/locked-env/bin/python -m pytest -q`: **94 passed in 52.81s**, no skips.
- Ruff lint/format and Prettier checks passed; `git diff --check` passed.
- The local HTML API reference was checked without any CDN scripts; prefixed OpenAPI remained available.
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
