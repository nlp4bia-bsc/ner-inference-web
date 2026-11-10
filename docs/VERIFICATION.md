# Latest: Administrator approval, all projects, erasure and custom quotas (0.11.0)

Executed 2026-11-10 with Python3.12.14, FastAPI0.141.1, Starlette1.6.0,
Pydantic2.13.4, torch2.15.0+cpu, Transformers5.22.1, Playwright1.62.0 and
local Chromium on Linux. All accounts/documents/checkpoints are synthetic fixtures.

- `/tmp/ner-ui-env/bin/python -m pytest -q`: **300 passed, 121 browser cases
  skipped**, 109.45 seconds. Browser cases require the explicit opt-in below.
- Full current CI browser command below: **156 passed, one synchronization
  assertion failed**, 540.90 seconds, with Chromium and axe WCAG2/2.1/2.2 AA checks.
  The failing case read computed style from an SVG node detached by live redraw,
  yielding an empty string. Its color check now retries against the current node
  and requires the exact reference pink for both owner and administrator. The
  entire affected six-case matrix then passed (below). All selected cases have
  passing evidence across these runs; there was no third full run. The full
  selection contains **121 browser cases and 36 overlapping server cases**.
- After the final route enum, audit-target links and responsive changes,
  `tests/test_admin_workflows.py tests/test_auth_migrations.py
  tests/test_locale_catalogs.py`: **31 passed**, 27.86 seconds.
- Dedicated final administrator browser matrix `tests/test_admin_browser.py`:
  **6 passed**, 48.60 seconds, using root and `/ner`, 320/390/1440-pixel screens,
  actual signup/review/login/MFA/quota/project/account actions, reflow and axe.
  Reviewed desktop/mobile screenshots; the entity color is identical in owner
  and administrator viewers. Existing overlap/palette browser cases also pass
  in the full command at 320,390,1440 and3840 pixels.
- An initial full browser run exposed **8 old fixture assumptions** that public
  signup allowed immediate login (149 passed,8 failed). Synthetic account setup
  now explicitly approves those fixtures; no production bypass/test HTTP route
  was added. The new review tests use the real administrator endpoints/UI.
  Corrected auth matrix: **10 passed**, 67.14 seconds; corrected upload/model/
  localhost matrix: **38 passed**, 37.61 seconds. The subsequent full run includes
  those corrections; its only failure was the detached-node test assertion above. Counts are not summed across reruns.

```bash
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js BROWSER_TESTS=1 \
  /tmp/ner-ui-env/bin/python -m pytest -q \
  tests/test_browser.py tests/test_viewer_browser.py tests/test_ui_v3.py \
  tests/test_auth_browser.py tests/test_design_browser.py \
  tests/test_overlap_readability.py tests/test_simple_registration.py \
  tests/test_on_demand_models.py tests/test_submission_security.py \
  tests/test_local_origins.py tests/test_document_management_browser.py \
  tests/test_model_progress_browser.py tests/test_admin_browser.py
```

Security cases exercise pending/rejected login and stale-session denial,
verification independent of approval, request-profile visibility/escaping,
CSRF/origin/mass-assignment rejection, direct/encoded administration URLs,
ordinary-user isolation, authorized cross-owner reads/exports/erasure, role
revocation while a destructive action waits on a lock, account deletion during
upload, quota lowering during upload, zero/reset/increased quotas, last-admin
protection, interrupted erasure/retry and late-worker fencing. Migration tests
construct the previous schema and preserve existing administrator/MFA/session
records; injected DDL failure rolls back and a retry succeeds.

- `python -m scripts.inventory_routes`: **96 method/route pairs** recorded in
  [route inventory](ROUTE_SECURITY_V4.md).
- Ruff lint and format: **pass**, 137 Python files formatted.
- Prettier check for modified authored JS/CSS: **pass**.
- `work/release-tools/bin/python -m bandit -r app scripts -ll`: **no medium/high
  findings** (seven low-severity findings; not a clean-all-levels claim).
- `work/release-tools/bin/python -m build --no-isolation --outdir
  /tmp/ner-admin-build`: wheel and sdist **pass**. Archive inspection confirms the
  new erasure module/project template are packaged and private `gazetteers/`,
  `storage/`, `work/` and `.env` are excluded. `git diff --check` passes.
- One existing AnyIO pytest-plugin deprecation warning is present. Docker images
  and GPU execution were **not rebuilt/retested** for this account/UI release;
  container/proxy configuration and dependency locks are unchanged. No new SMTP,
  real clinical checkpoint accuracy, confidential terminology or production TLS
  delivery claim is made by these tests.

See [administration](ADMINISTRATION.md), [current security review](security/admin-approval-review.md)
and the updated privacy/terms drafts. Older V4 reports remain historical evidence
for the previous owner-only administrator policy.

# Previous: Reference color families and separated secondary categories (0.10.6)

Executed 2026-11-10 in the same Python 3.12 / CPU / Chromium environment below:

- `BROWSER_TESTS=1 AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js
  SCREENSHOT_OUTPUT=work/restored-palette-previews /tmp/ner-ui-env/bin/python -m
  pytest -q tests/test_overlap_readability.py`: **36 passed**, 114.85 seconds.
  Checks include identical caption/bracket colors for the four reference categories,
  correct shared-gradient colors and limits, keyboard selection, source conservation,
  minimal overlap depth and geometry at 320, 390, 1440 and 3840 pixels.
- `/tmp/ner-ui-env/bin/python -m pytest -q tests/test_design_v5.py
  tests/test_viewer_api.py tests/test_locale_catalogs.py`: **13 passed**, 4.94 seconds.
  The full server and CI browser suites were not repeated for this CSS palette change.
- DISEASE is light pink, SYMPTOM orange, PROCEDURE blue and MEDICATION green.
  Captions and shared brackets use the identical canonical color. Dark caption text
  on light fills preserves these requested colors instead of darkening the fill.
  Reviewed the four-category synthetic screenshot at 1440 pixels.
- [Current palette measurements](security/v0.10.6-entity-palette.json) cover all
  thirteen registered categories: minimum caption-text contrast **4.636:1**, minimum
  inline text contrast **11.343:1**. Minimum normal-vision pairwise OKLab distance
  increased from **0.040845** to **0.128207**. This does not certify accessibility for
  every color-vision deficiency; category names and IDs remain available.
- Ruff lint/format, Prettier, Bandit medium/high checks and wheel/sdist build pass.
  Private data remain excluded from packages. One existing pytest plugin
  deprecation warning is present. No runtime dependency or model changes.

# Previous: One shared multicolor bracket above each annotated region (0.10.5)

Executed 2026-11-10 in the same Python 3.12 / CPU / Chromium environment below:

- `/tmp/ner-ui-env/bin/python -m pytest -q`: **272 passed, 115 browser cases
  skipped**, 89.60 seconds.
- `BROWSER_TESTS=1 AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js
  SCREENSHOT_OUTPUT=work/shared-bracket-previews /tmp/ner-ui-env/bin/python -m
  pytest -q tests/test_overlap_readability.py`: **36 passed**, 128.80 seconds.
  Tests independently reconstruct overlap-connected regions from fixture offsets
  and require exactly one shared bracket per region. The SVG contains only the
  caption rectangles: no extra filled source bands. Each bracket sits immediately
  above its source glyph box, including wrapped text, accents and emoji.
- Geometry still checks minimal tower depth, independent caption centering over
  each entity, exact source text, original span offsets, keyboard focus and resize
  behavior at 320, 390, 1440 and 3840 pixels. Real gradients retain the canonical
  palette. A hand-specified partial overlap checks both category colors and verifies
  that the second color stays within the actual intersection.
- Viewer/form/live-progress regressions and repeated pair/triple overlaps:
  **31 passed, 28 deselected**, 89.29 seconds, with browser/axe enabled and
  `tests/test_viewer_browser.py tests/test_ui_v3.py tests/test_model_progress_browser.py
  tests/test_overlap_readability.py -k 'not test_overlaps_do_not_insert_text_or_change_character_layout
  or pair-plus-separated or triple-plus-separated'`. Eight overlap cases are
  repeated here; this is not a second full geometry matrix.
- An initial color-boundary assertion exposed SVG scaling rounding of about
  0.03 SVG pixels, rather than an annotation-boundary change. That comparison now
  allows at most 0.25 SVG pixels (less than one display pixel at the tested scales).
- Reviewed the synthetic nested-entity screenshot at 1440 pixels: labels stand
  independently above one thin, unfilled shared bracket per source region. The
  bracket itself carries the overlapping colors; no separate bar is drawn.
- Ruff lint/format, Prettier, Bandit medium/high checks and wheel/sdist build pass.
  Private data remain excluded from packages. Hint text covers all sixteen UI
  languages. One existing pytest plugin deprecation warning is present.

# Previous: Persistent span brackets and overlap color bands (0.10.4)

Executed 2026-11-10 in the same Python 3.12 / CPU / Chromium environment below:

- `/tmp/ner-ui-env/bin/python -m pytest -q`: **272 passed, 115 browser cases
  skipped**, 99.56 seconds in the final run.
- `BROWSER_TESTS=1 AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js
  SCREENSHOT_OUTPUT=work/persistent-span-previews /tmp/ner-ui-env/bin/python -m
  pytest -q tests/test_overlap_readability.py`: **36 passed**, 138.88 seconds.
  Checks cover permanent bracket visibility, minimum overlap depth, unchanged
  source text/offsets, label centering, wrapped spans, nested/crossing overlaps,
  Unicode, keyboard selection, resize/scroll and accessibility at 320, 390, 1440
  and 3840 pixels. The shared band is checked against hand-specified intervals;
  its rectangles must not collide with source glyphs, captions or brackets.
- Viewer, form and live model-progress regressions plus repeated pair/triple
  overlap cases: **31 passed, 28 deselected**, 92.24 seconds, using
  `tests/test_viewer_browser.py tests/test_ui_v3.py tests/test_model_progress_browser.py
  tests/test_overlap_readability.py -k 'not test_overlaps_do_not_insert_text_or_change_character_layout
  or pair-plus-separated or triple-plus-separated'` with browser/axe enabled.
  Eight overlap cases are repeated in this group; this is not a second full matrix.
- Reviewed synthetic screenshots, including nested clinical-label spans at
  1440 pixels. All colored brackets remain visible before/after selection, and
  shared bands show multiple category colors over their exact common portions.
  Hint text is translated in all sixteen interface languages.
- An initial parallel run encountered a concurrent-admission 403 assertion and
  two color assertions during SVG redraw. The final full server/matrix runs above
  pass. Color checks now query and measure the active SVG in one browser evaluation
  instead of holding nodes across a possible ResizeObserver replacement.
- Ruff lint/format, Prettier, Bandit medium/high checks and wheel/sdist build pass.
  Private data remain excluded from packages. One existing pytest plugin
  deprecation warning is present. No dependency or deployment configuration changes.

# Previous: Named jobs, Other language and persistent tower colors (0.10.3)

Executed 2026-11-10, Python 3.12, Torch 2.15.0+cpu, Transformers 5.22.1,
ner_lab pinned to `8640d4797b081a5f6b66d9b45c11269542a79a26`, system Chromium:

- `/tmp/ner-ui-env/bin/python -m pytest -q`: **272 passed, 115 browser cases
  skipped**, 113.30 seconds. Metadata tests cover TXT, real ZIP and pasted inputs,
  custom title preservation, old history/status fallback, control/length validation,
  multilingual eligibility and owner document metadata.
- The CI Chromium/accessibility file list ran in two disjoint groups with
  `BROWSER_TESTS=1 AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js`:
  `test_ui_v3.py test_overlap_readability.py test_design_browser.py`: **66 passed**,
  330.72 seconds; remaining CI files: **85 passed**, 196.33 seconds. **151 passed,
  no skips** in total. This includes all sixteen UI locales, root and `/ner`,
  inspector glyph geometry, unchanged overlap depth/offsets, colors before
  selection, and title/language persistence across uploads, tabs and locale changes.
- Real tiny CPU classifier integration exercises cold download and warm reuse
  for both Spanish and Other, including native text statistics and exports.
  It uses a synthetic local HTTP Hub and an ordinary token classifier, not
  downloaded clinical weights. The separate controlled MTL adapter test verifies
  routing/publication; it does **not** establish compatibility of the existing
  custom MTL architectures. Those still require their own compatible runtime adapter.
- All 38 existing CSS palette backgrounds have at least **5.45:1** contrast with
  the new white tower captions. Reviewed a synthetic overlapping-entity screenshot
  at 1440 pixels. Only the active annotation reveals its span lines.
- Ruff lint/format, Prettier, Bandit medium/high checks and wheel/sdist build pass.
  Package inspection excludes gazetteers, Parquet, FAISS indices, private storage,
  certificates, `.env` and development artifacts. No dependency changes or database
  migration are required. Docker deployment configuration is unchanged.
- One pytest plugin deprecation warning is present; no final verification failures.

Commands use an isolated verification environment created for this execution;
this does not change the deployment's Conda environment or Docker images.

# Previous: Fuzzy match, inspector columns and public Docker deployment (0.10.2)

Executed 2026-11-07:

- Server suite: **260 passed, 114 browser cases skipped**, 96.39 seconds.
- Full CI Chromium/accessibility file list: **149 passed**, no skips,
  455.86 seconds. Form/summary, model progress and inspector show Fuzzy match and
  their visible text excludes the algorithm name; the submitted API method remains
  unchanged. Inspector text geometry checks labels and values across all sixteen
  UI languages at 320, 390, 1440, 1920 and 3840 pixels, for root and `/ner`.
- Focused form/inspector checks before the final expanded matrix: **4 passed**,
  19.03 seconds, including axe. Full final results above include the expanded
  geometry and progress/inspector naming checks.
- Ruff lint/format pass. The matching implementation, offsets and persisted
  normalization method/threshold contracts are unchanged.
- Compose v2.40.3 validates base CPU, GPU, public CPU and public GPU configurations.
  `COMPOSE_FILE` loaded from a private sample env selects the right services and
  build profile. Both services share the external origin
  `https://temu.bsc.es:18443`; the public profile uses production/Secure cookies,
  preserves the internal shared data volume and publishes TLS on 18443.
  The application has no host HTTP port, avoiding a collision with an existing
  service on 8000; Compose 2.24.4+ resets the base port mapping. The private proxy
  supplies trusted client/scheme headers, without trusting incoming header values. GPU is
  optional and inactive by default. No NVIDIA hardware was available for testing.
- Real Caddy **2.11.9** ran the checked-in configuration against a synthetic local
  HTTP backend in disposable Docker containers. A temporary test CA and server
  certificate for the domain were used; curl verified that CA without disabling
  certificate validation. HTTPS returned 200, preserved Host including its public
  port and forwarded the HTTPS scheme. Test containers/network/certificates were
  removed. This was a local synthetic proxy check, not a deployment to BSC or a
  validation of an institutional certificate.
- The current application also ran in the native CPU verification runtime behind
  that real Docker proxy. Health, registration, login and authenticated session
  returned 200; Secure cookies were stored. An authenticated test-only transport
  probe confirmed HTTPS scheme and ignored spoofed client forwarding headers.
  The probe is not part of the application. A cached-image app smoke attempt hit
  the workspace VFS disk bound; application containers were not claimed as tested.
  All disposable containers, networks and temporary certificates were removed.
- Internal Docker service `web` is excluded from the proxy's outbound HTTP proxy,
  preserving other inherited proxy exclusions. This resolves the local Cloud
  test's initial upstream 403 without changing external network policy or turning
  off TLS verification.

The public quickstart uses CPU, a persistent `.env` and mounted private
certificates/Parquet files. The bundled proxy reuses an existing server certificate; port 80 need not be free. Future NVIDIA activation uses the optional overlay; CUDA 13.2
requires a compatible host driver and Container Toolkit. The existing machine certificate can be reused; the guide locates and checks its
hostname coverage. Neither host port 80 nor 443 is published by the Docker profile.
The actual final host, DNS/firewall and production certificate have not been configured in this session.
The Docker web/worker application images were not rebuilt here; Python package
builds and the existing CPU/native inference regression suite cover this release.

```bash
python3 -m pytest -q
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js BROWSER_TESTS=1 python3 -m pytest -q tests/test_design_browser.py tests/test_model_progress_browser.py
python3 -m ruff check app scripts tests
python3 -m ruff format --check app scripts tests
docker compose --env-file /dev/null config --quiet
docker compose --env-file /dev/null -f docker-compose.yml -f docker-compose.public.yml config --quiet
docker compose --env-file /dev/null -f docker-compose.yml -f docker-compose.public.yml -f docker-compose.gpu.yml config --quiet
```

See the [public Docker quickstart](DOCKER_QUICKSTART.md) for the exact setup,
private import permissions and optional complete Conda storage migration.

---

# Latest: unfinished HTML viewer and actual-overlap towers (0.10.1)

The pasted-text regression reproduced the reported 409 before the fix: **2 failed**
(root and `/ner`), both with `No annotated documents are available yet.` The test
captures HTML responses after DISEASE and before SYMPTOM while finished-document
count remains zero. Both HTML aliases and the Dashboard link now work, including
before the first annotation. Login, ownership, expiry and deletion checks remain.

Executed 2026-11-07 in the existing CPU/Chromium verification environment:

- Server suite: **260 passed, 112 browser cases skipped**, 95.10 seconds.
- Complete CI browser regression list: **147 passed**, no skips, 445.26 seconds.
  Includes all existing browser, ownership/revocation, document management,
  live progress and viewer checks, with the new cases below included.
- Actual backend unfinished-page browser regression: **2 passed**, 10.78 seconds,
  using both base prefixes and without mocking the HTML page or backend counts.
- Expanded overlap geometry suite: **32 passed**, 94.09 seconds, plus **4 clinical
  disjoint cases passed**, 13.09 seconds. A final clinical/scroll check passes all
  **4 cases**, 18.24 seconds. All use Chromium; axe runs where configured.
- Four viewport widths: 320, 390, 1440 and 3840. Geometry checks cover 1/2/3-level
  examples, short crowded labels, independent clinical symptoms/medications,
  crossing chains, dense overlaps, Unicode/graphemes and line wrapping. A seeded
  100-graph property check validates minimum simultaneous overlap depth and
  conflict-free lanes. No minimum height is inferred from caption widths.
- Checks verify source reconstruction, exact glyph-coordinate range endpoints,
  centered readable tags, no collisions, no font compression, one caption per
  entity, selected-only range marks, keyboard focus, scroll preservation,
  responsive font scale and language-independent colors. The hint is translated
  in all sixteen UI languages.
- Ruff lint/format and Bandit `-ll` pass. Wheel/sdist 0.10.1 builds pass and exclude
  confidential dictionary/storage/Parquet/FAISS/ZIP/SQLite data. No dependencies,
  database migrations or inference changes are introduced. Docker was not rebuilt.

Commands:

```bash
python3 -m pytest -q
python3 -m pytest -q tests/test_live_viewer_access.py
BROWSER_TESTS=1 python3 -m pytest -q tests/test_model_progress_browser.py -k real_html
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js BROWSER_TESTS=1 python3 -m pytest -q tests/test_overlap_readability.py
python3 -m ruff check app scripts tests
python3 -m ruff format --check app scripts tests
python3 -m bandit -r app scripts -ll
python3 -m build --no-isolation
```

The old tests exercised APIs and a viewer backed by an already completed fixture;
they did not exercise the actual HTML route with zero finished documents. The new
server/browser regressions close that gap. Synthetic captures and design details:
[overlap review](OVERLAP_REVIEW.md). Source text, saved annotations and exports
are unchanged by visual spacing. For crossing chains, minimum actual depth takes
precedence over imposing a global short-to-long order that could require extra
rows. No clinical accuracy or production performance claim is made.

---

# Latest: durable document/model/category phases (0.10.0)

Executed 2026-11-07 in the existing CPU verification environment (Python 3.12.14,
Torch 2.15.0+cpu, Transformers 5.22.1, FAISS CPU 1.15.1, Chromium). No production
confidential dictionary, remote Conda installation or clinical inference workload
was available. My documents selection/deletion was intentionally left unchanged.

- Final server suite: **258 passed, 90 browser cases skipped**, 78.30 seconds.
- Full CI Chromium/accessibility file list: **125 passed**, no skips,
  393.89 seconds. Includes root and `/ner` deployments, all existing overlap,
  document deletion/ownership, locales/reflow and native browser interactions.
- Dedicated progress/live-viewer browser checks: **4 passed**, 22.48 seconds.
  The added tests open a raw document, add NER, then change normalization without
  changing mention counts. They verify automatic refresh, selected concept
  inspection, preserved text search and no browser exceptions.
- Final phase/recovery/incremental/deletion target set: **17 passed**, 6.30 seconds.
- Ruff lint/format pass; Bandit `-ll` reports no medium/high findings. Wheel/sdist
  0.10.0 builds pass, contain the phase module and exclude private gazetteer,
  storage, Parquet, FAISS, ZIP and SQLite data. Docker images were not rebuilt;
  this release adds no dependencies or Compose configuration changes.

```bash
python3 -m pytest -q
python3 -m pytest -q tests/test_phased_processing.py tests/test_incremental.py tests/test_document_management.py
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js BROWSER_TESTS=1 python3 -m pytest -q tests/test_model_progress_browser.py
python3 -m ruff check app scripts tests
python3 -m ruff format --check app scripts tests
python3 -m bandit -r app scripts -ll
python3 -m build --no-isolation
```

The complete browser run used the unchanged CI browser file list, with the two
new live-viewer cases included. Synthetic callbacks assert all corpus batches of
one NER member run before the next; DISEASE normalization is published in every
document before SYMPTOM starts. Fault injection covers interruption during the
next category, completed-member preservation, terminal-failure preview reads,
restart without repeating NER and a crash after atomic preview replacement but
before DB counts. The spawned supervisor timeout test asserts `reason=JobTimeout`.
Existing native NER/CRF/FAISS, statistics equality, offset, private ownership,
repackaging and stale-worker deletion checks remain passing.

The supplied historical log ended in `success=False` without a cause. It supports
investigating a timeout but does not prove one; no claim is made that this remote
failure was reproduced. New sanitized logs identify configured timeout, child
exit status and interruption reason. Old jobs without saved publications cannot
reconstruct annotations from progress logs. Phase checkpoints preserve completed
member/category work; partial FAISS embedding builds are not resumable. There are
no new clinical accuracy, production throughput or memory benchmark claims.

---

# Latest: Parquet lexical normalization and DT4H language grouping (0.9.0)

Executed on 2026-11-07 with Python 3.12.14, RapidFuzz 3.14.6, PyArrow 26.0.1,
Torch 2.15.0+cpu, Transformers 5.22.1 and FAISS CPU 1.15.1 in an isolated
verification environment. The application remains compatible with native Conda;
the isolated environment is only this workspace's test harness.

- Server suite: **249 passed, 88 browser checks skipped**, 65.82 seconds.
- Final lexical regression suite after five additional cases: **21 passed**,
  10.92 seconds. The additional cases check old queued requests, inclusive 0.8,
  threshold extremes, Unicode equality/ambiguity, legacy Parquet key building
  and lexical exports/deletion repackaging without the current dictionary.
- Final metadata suite with the exact confirmed ZIP directory prefix:
  **24 passed**, 1.94 seconds.
- New real Chromium normalization interaction checks: **2 passed** (root and
  `/ner` prefix), 14.24 seconds, including axe with bi-encoder warning visible.
- Full Chromium/accessibility regression suite (the CI browser file list):
  **123 passed**, no skips, 360.28 seconds. Root and `/ner`, uploads, live model
  progress, ownership/deletion, overlap rendering and locale/reflow checks pass.
- Ruff lint/format pass. Bandit `-ll` reports no medium/high severity findings.
  Wheel/sdist 0.9.0 build passed; archive inspection found no confidential
  gazetteer/storage, Parquet, FAISS, ZIP or SQLite files.

Commands (use `python3` in your active Conda environment):

```bash
python3 -m pytest -q
python3 -m pytest -q tests/test_lexical_normalization.py
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js BROWSER_TESTS=1 python3 -m pytest -q tests/test_design_browser.py -k normalization
python3 -m scripts.benchmark_normalization
python3 -m ruff check app scripts tests
python3 -m ruff format --check app scripts tests
python3 -m bandit -r app scripts -ll
python3 -m build --no-isolation
```

Coverage includes 28 synthetic files in the confirmed seven-language directory
layout with misleading ontology language columns, metadata-only preflight and
explicit column/path policies. Default lexical sessions reject accidental neural
or SQLite calls in a regression guard, reuse Arrow dictionaries across batches,
and leave valid no-match jobs completed. Matching is compared with brute-force
normalized edit distances over 4,500 forms and duplicate primary concepts.
Explicit bi-encoder tests exercise the real tiny Transformer, native `fit_faiss`
and `get_candidates`, warm/cold FlatIP reuse and multiple batches. Existing
medication source-reference, offset, private ownership and deletion suites run.
The confidential binary ZIP was not available here; its confirmed directory
layout and metadata were reproduced synthetically. Production terminology
quality and clinical accuracy were not measured. Docker images were not rebuilt
in this change; existing Compose defaults/mounts are unchanged and lock files add
RapidFuzz. No full production-size neural index was fitted.

## Synthetic lookup measurements

Reproduction: `python3 -m scripts.benchmark_normalization`. This creates temporary
synthetic Parquets, runs the production matcher and deletes synthetic data.
[Measured JSON](benchmarks/v0.9-parquet-lexical.json) records Python/platform,
counts, compressed size, loading, exact/fuzzy queries and cumulative process RSS.
Four exact and three previously unseen fuzzy queries run at threshold 0.8, top 5.
These are measurements of lexical lookup, not NER or a clinical dictionary.

| Synthetic pairs/forms | Concepts | Load incl. hash | Four exact queries | Three fuzzy queries | Process peak RSS |
|---|---|---|---|---|---|
| 100,000 | 100,000 | 0.045 s | 0.00031 s | 0.161 s | 217 MiB |
| 1,000,000 | 150,000 | 0.611 s | 0.00033 s | 0.946 s | 508 MiB |

Compressed Parquet sizes were 1.88 and 18.74 MiB. Repeated fuzzy queries use the
job-local LRU (0.00023 and 0.000013 s for three queries). RSS is the whole process
high-water mark, cumulative across cases, including Arrow/string generation;
it is not isolated matcher allocation. Measurements ran alongside browser tests
and vary with contention and disk cache (a preceding million-row run loaded in
0.277 s and queried in 0.608 s). Long distinct unmatched mentions can still scan
many forms. There is no assertion that Parquet universally beats a database,
or that these timings predict confidential corpus performance.

---

# Latest: mixed ISO/UMLS terminology metadata (0.8.2)

Server regression: **233 passed, 86 browser-only cases skipped in 61.13s**.
Targeted metadata/list/native-normalization checks: **35 passed in 7.50s**.

```sh
OMP_NUM_THREADS=1 /tmp/ner-web-progress-env/bin/python -m pytest -q
OMP_NUM_THREADS=1 /tmp/ner-web-progress-env/bin/python -m pytest -q \
  tests/test_gazetteer_metadata.py tests/test_gazetteer_lists.py tests/test_normalization.py
```

A synthetic 28-file ZIP covers all four categories in es/en/cs/nl/it/ro/sv,
mixing ISO two-letter languages and UMLS LAT codes in medication dictionaries.
Additional cases cover ISO 639-2 aliases, regional/name forms, Arrow single-
language list cells, explicit overrides and ambiguous/unknown metadata. The full
archive metadata check runs before preparation and reports every invalid file
without printing dictionary values or registering partial terminology. Inspection
still works when the filename alone cannot identify its language/category.

Ruff lint/format, git diff --check and Bandit checks on the changed importer and
metadata helper pass, with no Bandit findings. No browser-facing behavior or
inference dependencies changed; browser cases were not rerun for this CLI fix.
The actual private ZIP/remote Conda deployment has not been executed here. The
reported exception does not reveal its raw language values; support for standard
UMLS/ISO metadata and improved inspection are verified with synthetic fixtures.

---

# Historical: DT4H list import, medication identifiers and selected deletion (0.8.1)

Full CPU/Chromium regression: **295 passed in 425.14s**, without skips or failures.
The server-only run passes 209 cases (86 browser cases opt out in that run).
Focused document/progress browser checks pass eight cases under root and /ner,
including cross-page selection, refresh preservation, cancellation, deletion,
quota/lifetime counters and 375/1440/3840px reflow. Full verification command:

```sh
OMP_NUM_THREADS=1 AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=/tmp/selection-final-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=/tmp/selection-final-screens \
/tmp/ner-web-progress-env/bin/python -m pytest -q
```

The supplied worker log identifies the missing resource lookup before encoder or
FAISS execution. The subsequent import trace identifies the previous refusal of
list-valued terminology. Synthetic Parquet/ZIP fixtures reproduce the reported
columns and scalar/list cells, both SAB_code spellings, synonyms, positional
nulls, ambiguous multiple-code refusal and explicit pairing modes. The importer
preserves primary UMLS CUIs and merges secondary SAB references. An actual tiny
local bi-encoder/FlatIP test checks cold and warm index reuse, API annotation
contracts and multiple BRAT N references without changing the original T span.
All fixtures are synthetic; the confidential binary archive has not been read
here and its clinical content/scale has not been validated.

Selected deletion tests cover preflight denial of foreign/unknown IDs before
mutation, CSRF, empty selections, duplicate/idempotent requests, one generation
change per project, multiple projects, retained quota, lifetime history and
repackaging. The CLI reports read-only terminology setup without dictionary terms.
Progress and error provenance use enumerated normalization reasons; model error
messages do not contain raw exception strings or clinical text.

[82 axe scans](security/v8.1-axe.jsonl) have zero automatic violations;
52 scans have incomplete rules, so this is not a full WCAG certification.
Ruff lint/format, Prettier on changed JS/CSS, git diff --check and Bandit medium/
high checks pass (six low-severity findings). Wheel/sdist 0.8.1 build; packaged
updated runtime/UI code matches the checkout and contains no Parquet, FAISS or
private gazetteer directory. No dependency changes or schema migration were
needed. No Docker or remote Conda deployment was performed in this change.

---

# Historical: model progress, owner project deletion and local Compose (0.8)

Final full CPU/Chromium regression: **286 passed in 435.17s**, no failures or
skips. Commands executed from the checkout root (Python 3.12, Torch 2.15.0+cpu,
Transformers 5.22.1, FAISS CPU 1.15.1, Chromium):

```sh
OMP_NUM_THREADS=1 AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=/tmp/ner-progress-final-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=/tmp/ner-progress-final-screens \
/tmp/ner-web-progress-env/bin/python -m pytest -q
```

The additional final native inference/normalization/supervisor set passes
**17 cases in 25.03s**. The per-model/generation/deletion/recovery set passes
**19 cases in 15.75s**. Two additional root/prefix browser runs with explicit
worker-unavailable and NER/FAISS accessibility scans pass in 14.50s.

Coverage includes real native Transformer batches reported before document
publication, prediction equality with/without reporting, one forward per batch,
native CRF trainer selection, cold FlatIP build and warm disk reuse counters,
worker heartbeat expiry, foreign-owner denial, stale generation rejection,
per-member restoration from publications, deleting queued and completed projects,
bulk owner-only deletion with CSRF, retained-quota refresh and permanent upload
history. Chromium exercises project/bulk deletion and 375/1440/3840px progress
cards under both root and /ner. The original overlap/Unicode/centering/order/
click-only-lines suite passes, including 4K geometry.

The first full run exposed two outdated browser quota assertions (100 versus
0 / 100), a screenshot interrupted by the Docker disk-space experiment, and a
real sticky progress panel obscuring a viewer button. The quota assertions now
match the retained-quota contract. Expanded panels and terminal summaries scroll
normally; only collapsed active summaries can stick. The final full rerun above
passes with the original accessibility rules enabled.

[80 axe scans](security/v8-axe.jsonl) contain zero automatic violations, including
the new unavailable-worker and NER/FAISS cards. 52 scans have incomplete rules,
so these results do not certify full WCAG conformance. Ruff lint/format, Prettier
for changed JS/CSS, `git diff --check` and Bandit medium/high checks pass (six
low-severity Bandit findings). Wheel/sdist 0.8.0 build successfully; packaged
progress, worker, native reporting and document UI code match the checkout.
Neither package contains confidential Parquet/FAISS/gazetteers data.

Compose configuration was evaluated with `/dev/null` as its env file and all
interpolated runtime variables removed from the process. Both services resolve
the expected loopback HTTP/on-demand/online defaults without manual exports;
web uses no email delivery/verification. The web Docker target built successfully
with unchanged HTTP dependency locks and the session CA secret. A separate
web+CPU-worker container smoke was attempted but could not be completed: Docker
VFS exhausted the available disk while creating the extra worker container. A
follow-up bind-mounted HTTP smoke did not reach a healthy service and is not
counted as passing. Temporary containers, volume, network and the new image/cache
records were removed; existing deployments were not replaced. Full worker-image
startup is therefore not claimed by this release check. CI now exercises Compose
without copying an env file first, and includes the new progress browser module.

The worker was validated through actual native subprocess inference with tiny
synthetic weights. No deployment or diagnosis of the user's remote Conda host,
clinical accuracy, full private dictionary scale or GPU throughput is claimed.
The new runtime CLI/logs provide the interpreter, shared database path and worker
state needed to diagnose that host without exposing document text or credentials.

---

# Historical: loopback aliases and missing inference runtime (0.6.3)

Local development/test with non-Secure cookies accepts the explicit
`localhost`/`127.0.0.1` alias pair on the same scheme and port. Production,
Secure-cookie deployments, unrelated domains/IPs, other ports/schemes and
`0.0.0.0` retain their restrictions. CSRF HMAC/session proof and cross-site Fetch
Metadata rejection remain mandatory. Host comparisons normalize default ports
and case; malformed origins are rejected safely. Request-origin diagnostics record
bounded scheme/host/port and enumerated Fetch Metadata without paths/queries,
credentials, cookies, patient text or body data.

Accepted private links retain the validated browser origin so localhost submission
does not jump to 127.0.0.1 and lose its host-only session cookie. Untrusted Host
values cannot choose that link's origin. API cases cover both alias directions,
root and `/ner`, required CSRF proof, touch and ZIP submission, private-page
access and malicious Host fallback. Real Chromium on localhost, against a server
configured for 127.0.0.1, signs in, uploads a nested ZIP and opens its private link
at both root and `/ner`. A canonical-host session check proves cookies were not
shared between domains.

The user's failed job had no installed inference libraries. A worker now checks
module availability before touching storage, recovering or claiming jobs. Missing
modules produce a direct installation instruction with the effective interpreter;
no model weights are imported/downloaded by this check. Web stays lightweight.
Safe per-model errors also name missing top-level inference modules from a fixed
allowlist without exposing exception strings. A previously FAILED job remains
failed; it must be resubmitted after repairing the environment.

The focused aliases/configuration/submission/cache set passes **43 cases in
30.24s**, including isolation of a synthetic missing-module failure and log
privacy. These are mechanics tests, not clinical-model validation.

Full regression: **251 passed in 376.38s**, zero failures/skips:

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/local-aliases-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/local-aliases-release \
work/locked-env/bin/python -m pytest -q
```

[72 axe scans](security/v6.3-axe.jsonl) have zero automatic violations; contrast
remains incomplete in 44 scans, so these do not certify WCAG conformance. Ruff
lint/format (105 Python files), Bandit medium/high checks and wheel/sdist 0.6.3
builds pass. The actual configuration CLI accepts localhost for a local
127.0.0.1 configuration using the same origin policy as HTTP admission. Packaged
origin, worker, pipeline, runtime and API code match the checkout. No native
library versions changed; no model weights are bundled. No installation/deployment
on the user's remote machine is claimed.

---

# Historical: native configuration diagnostics and workspace verification policy (0.6.2)

The user's actual deployment runs native Uvicorn and a Python worker on another
machine, reached through a forwarded port. Earlier local-container recreation did
not change that remote process. Its log still reports `https://localhost:8000`;
changing a private `.env` cannot override a stale process environment variable.
Settings precedence is preserved, and origin/CSRF checks remain mandatory.

`python -m scripts.check_config --expect-origin http://127.0.0.1:8000` reports the
active interpreter, checkout/config paths, safe effective settings and their
sources, plus inference-module availability without importing model weights or
making network requests. Real CLI subprocess checks reproduce a stale shell value
overriding a correct `.env` (exit 1) and explicit corrected values (exit 0).
Tests assert SMTP/Hub credentials never appear in the report. Native/forwarded-port
instructions distinguish browser origin, per-terminal configuration, library
installation, web startup and worker startup. HTTP-only requirements are not
presented as sufficient for inference. Existing private settings/data need no reset.

The workspace had a separate rendering bug: its verification notice depended
only on `email_verified_at`, even when verification was disabled. Dashboard and
My jobs now also honor `REQUIRE_EMAIL_VERIFICATION`. No verified timestamp is
fabricated; registration/session/authorization policy is unchanged. Acceptance
checks cover both policies, root and `/ner`, and English/Spanish/Catalan. Existing
real Chromium default-registration cases now also assert the notice/link is absent.

The focused configuration/registration/ZIP set passes **21 cases in 23.73s**.
The strengthened production-registration cases reproduce the old notice before
the fix. A legacy production-settings test also depended on the absence of a
local `.env`; it now explicitly constructs production settings so local development
configuration does not invalidate its safety checks. The corrected isolation set
passes **7 cases in 1.50s**.

Final full regression with the local `.env` present: **230 passed in 367.60s**,
zero failures/skips, using:

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/runtime-config-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/runtime-config-release \
work/locked-env/bin/python -m pytest -q
```

[72 axe scans](security/v6.2-axe.jsonl) have zero automatic violations. Color
contrast remains incomplete in 44 scans, so these do not certify WCAG conformance.
Ruff lint/format (102 Python files), Bandit medium/high checks and wheel/sdist
0.6.2 builds pass. Packaged dashboard/API source matches the checkout. The initial
full run was interrupted after identifying the local `.env` isolation issue;
the final complete run above includes that corrected production validation.

This release is tested in the selected environment. The user's remote machine
must pull the commit, apply its own effective settings and restart both processes;
no remote deployment or clinical-model execution on that machine is claimed.

---

# Historical: local ZIP submission and origin diagnosis (0.6.1)

The running service was configured for `https://localhost:8000` while the user
opened `http://127.0.0.1:8000/annotate?lang=en`. Its real XHR Origin therefore failed
the mandatory origin check even with a valid session/CSRF token. Local setup now
uses the exact `http://127.0.0.1:8000` origin from `.env.example`, development cookies
and `MAIL_BACKEND=none`. Production retains its HTTPS/Secure-cookie requirements.
No origin allowlist, forwarding-header trust or CSRF bypass was added.

Seven new acceptance cases reproduce the original mismatch, check the documented
local settings with ZIP uploads and eight selected models at root and `/ner`,
and exercise a genuine server CSRF rejection/retry in Chromium. Missing/invalid
proof remains rejected before admission. Selected files/models survive rejection,
the obsolete upload-complete status clears, and a corrected retry receives 202.
The new cases pass **7/7 in 7.70s**; their pre-fix runs fail as expected.

A real Chromium smoke against the built 0.6.1 web container, using isolated tmpfs
data and `/ner`, registers an account without mail, signs in through the HTML
form with a four-character password, submits a nested two-TXT ZIP with eight
models and receives **202 QUEUED** plus the correct private URL. Its request has
matching Origin and same-origin Fetch Metadata. This verifies submission, not
clinical inference. The temporary container/data are removed afterward.

A mismatched origin now returns a localized service-address message instead of
suggesting a reload. Private debug records identify `reason=origin_mismatch` and
the configured origin, with no patient text, ZIP content, cookie or CSRF proof.
Full regression: **224 passed in 378.72s**, zero failures/skips, using:

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/submission-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/submission-release \
work/locked-env/bin/python -m pytest -q
```

[72 axe scans](security/v6.1-axe.jsonl) have zero automatic violations; color
contrast remains incomplete in 44 scans, so these do not certify WCAG conformance.
Ruff lint/format (100 Python files), changed-JS Prettier, generated translations
and Bandit medium/high checks pass. Wheel/sdist 0.6.1 and the updated web image
build successfully. The worker retains the exact native CPU libraries through
the previously documented local VFS override; no neural dependencies changed.
Private local environment settings are excluded from Git. Both local services
are recreated against the existing data volume; changing cookie policy requires
a fresh login. Production retains its explicit HTTPS/Secure configuration.

---

# Historical: on-demand models and independent failures (0.6.0)

Full regression: **217 passed in 384.94s**, zero failures/skips. The nine new
on-demand cases passed separately in 12.06s; the broader native/incremental set
passed 21 cases in 26.02s before the complete run.

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/on-demand-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/on-demand/release \
work/locked-env/bin/python -m pytest -q
```

Coverage includes all 48 configured repository entries selectable without local
weights, activation or receipts; independent model exceptions/malformed spans;
no fabricated success when all models fail; safe debug logs; and actual Chromium
submission of an uncached configured model at root and `/ner`.

The real Hugging Face client downloads a saved tiny random BERT token classifier
from an isolated local HTTP Hub fixture. Native CPU inference preserves Unicode
spans, original BIO labels and canonical mappings; a second job reuses the cache
without HTTP requests. A genuine fixture HTTP 404 is isolated while another model
successfully publishes partial results. Immutable job revision pins and offline
warm reuse are covered. These are synthetic mechanics tests, not clinical-model
accuracy or compatibility validation.

[72 axe-core scans](security/v6-axe.jsonl) have zero automatic violations; contrast
remains incomplete in 44 scans, so these results do not certify WCAG conformance.
Ruff lint/format (99 Python files), JS/CSS Prettier, generated translations and
Bandit medium/high checks pass. Wheel/sdist 0.6.0 build successfully; the packaged
model, pipeline, configuration and UI source files match the repository.

Both web and default CPU worker images build without downloading model weights.
This selected environment uses Docker VFS on a small disk; creating a standalone
native worker container exhausted space because VFS duplicated its libraries.
For local runtime smoke only, the web-based worker container mounts the exact
built CPU image's site-packages read-only. Torch 2.10.0+cpu, Transformers 5.22.1 and
the pinned ner_lab import successfully there. This machine-specific override is
ignored, not part of the portable Compose deployment. The committed Compose uses
separate web/worker images and a shared persistent model cache as documented.

Running root web/worker report healthy/ready. An isolated `/ner` container checks
registration without SMTP, four-character login, duplicate email rejection, all
48 configured repositories available in the cold catalog, annotation access,
role boundaries and logout. The isolated container uses ephemeral data and is
removed afterward; existing application data is preserved. No BSC production
deployment is claimed.

This session's outbound proxy rejects CONNECT to huggingface.co with HTTP 403.
The real public clinical repositories could not be downloaded here. Deployment
must allow Hugging Face and its download/CDN/Xet hosts; no policy bypass or claim
of live clinical-model success is made. See [ON_DEMAND_MODELS.md](ON_DEMAND_MODELS.md)
for cache lifecycle, error handling, supported formats and runtime requirements.
Earlier authentication, original offsets, viewer, ownership and retention
contracts remain covered by the complete regression suite.

---

# Historical: V5.4 registration without email verification (0.5.4)

Full regression: **208 passed in368.86s**, zero failures/skips. Focused auth checks
also passed **36/36 in21.62s**. Eight new acceptance cases cover production HTTPS
registration with no mail backend, root/prefix routes, four-character passwords,
duplicate normalized emails, concurrent registration, authenticated job admission,
password change/revocation and administrator bootstrap/MFA without email proof.
Four real Chromium cases exercise the default no-mail form at390/1440px and both
root and `/ner`, including three-character/two-emoji rejection and immediate login.
The legacy verification cases explicitly opt in to that optional policy; they
continue to cover token consumption, recovery, SMTP gating and unverified denials.
The existing reset regression now resets to an actual four-character password.

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/simple-registration-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/simple-registration/release \
work/locked-env/bin/python -m pytest -q
```

[72 existing design/viewer axe scans](security/v5.4-axe.jsonl) report zero automatic
violations; color contrast remains incomplete in44 scans. These do not certify
WCAG conformance. Ruff lint/format (96 Python files), JS/CSS Prettier, generated
translations and Bandit medium/high checks pass. Wheel/sdist0.5.4 and no-NLP Docker
build successfully; final auth modules/UI assets match the wheel and running image.

Root and `/ner` container smoke checks pass. The isolated `/ner` container uses
`MAIL_BACKEND=none` and registers/logs in with a four-character password, rejects
the duplicate email, opens annotation, preserves STANDARD/ADMIN boundaries and
logs out successfully. Root stays private and serves the new registration policy.
Local web/worker run0.5.4; no BSC production deployment is claimed.

The active policy is `REQUIRE_EMAIL_VERIFICATION=false`, with no verification mail
or token issued at registration. `email_verified_at` is not fabricated. Contact
links target fernando.gallego@bsc.es in the user's mail client; automatic server
mail still requires a mail transport. See [AUTHENTICATION_V4.md](AUTHENTICATION_V4.md)
for policy/operations. Ownership, CSRF, tiers, Argon2id, MFA, session revocation,
scientific offsets/exports, retention and earlier clinical/Torch limits remain.

---

# Historical: V5.3 selective marks and complete color coverage (0.5.3)

Final full regression: **200 passed in349.39s**, zero failures/skips. The12 focused
browser cases additionally passed in40.49s before the full run. They verify marks
are initially invisible even after inline selection, only the activated label's
marks appear, click-again hides them, and keyboard activation/resize preserve the
correct state. Existing source, offset, centering and size-hierarchy checks remain.

Color checks cover all54 original catalog labels against their declared canonical
families, accented/BIO equivalents, and all24 extension palettes. Unknown labels
receive stable colors instead of a shared gray. The raw PROFESION alias is
ambiguous between schemas; its display fallback is PROFESSION, while canonical
ANONYMIZATION remains distinct. No scientific labels/mappings were modified.

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/towers-focus-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/towers-focus/release \
work/locked-env/bin/python -m pytest -q
```

[72 axe-core scans](security/v5.3-axe.jsonl) report zero automatic violations;
color contrast remains incomplete in44 scans, so manual review remains necessary.
All37 active palette pairs have border, main-text and mention-metadata contrast
above4.5:1 in the [bounded static check](security/v5.3-entity-palette.json).
Ruff, Prettier, generated translation equality and Bandit medium/high checks pass.
Wheel/sdist0.5.3 and no-NLP Docker build successfully; packaged and running renderer
assets match repository bytes. Root and `/ner` smoke checks pass, including isolated
real registration/captured verification email/login/dashboard/logout. Local
web/worker run0.5.3; no BSC production deployment or clinical validation is claimed.

[Captures and review](OVERLAP_REVIEW.md) show both the quiet initial tower view and
the selected entity's marks. Earlier scientific/authentication/retention contracts
and operational limitations remain unchanged.

---

# Historical: V5.2 centered line towers (0.5.2)

Final complete regression: **200 passed in 355.15s**, zero failures/skips.
The strengthened overlap cases additionally pass **12/12 in53.64s**, comparing
the actual pixel heights of overlapping spans rather than only lane metadata.
They verify centered labels, shorter mentions below longer ones, complete line
block separation, no range-mark/label/source collisions, readable unscaled text
and keyboard focus before/after viewport resizing.

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/towers-centered-axe.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/towers-centered/release \
work/locked-env/bin/python -m pytest -q
```

[72 axe-core scans](security/v5.2-axe.jsonl) report zero automatic violations;
color contrast remains incomplete in44 scans and still needs manual review.
Ruff lint/format, static JS/CSS Prettier, generated translations and Bandit
medium/high checks pass. Wheel/sdist0.5.2 and no-NLP Docker build successfully;
final packaged/running renderer assets match repository bytes. Root and `/ner`
container checks pass, including real registration, captured email confirmation,
login, private dashboard and logout/revocation in the isolated test container.
Local web/worker run0.5.2; no BSC production deployment is claimed.

The [updated captures and review](OVERLAP_REVIEW.md) show independent towers per
source line, with centered labels and shorter-below/longer-above hierarchy.
Offsets, original text, canonical colors, inference/export rules, authentication
and retention remain unchanged. Earlier deployment/clinical limitations still apply.

---

# Historical: V5.1 annotation reader (0.5.1)

Final complete regression: **200 passed in 320.85s**, zero failures/skips. Includes
real Chromium account/owner/admin/MFA flows, root/prefix routing, incremental
publication, exports, original-coordinate validation, retention and native random
tiny-BERT CPU inference. This is not clinical-model accuracy validation.

```sh
AXE_CORE_PATH=work/design-a11y/node_modules/axe-core/axe.min.js \
AXE_REPORT=work/overlap-axe-release.jsonl BROWSER_TESTS=1 \
SCREENSHOT_OUTPUT=work/overlap-review/release \
work/locked-env/bin/python -m pytest -q
```

Twelve new browser cases cover inside-word, synthetic clinical multiword/nested,
18 dense crossing/equal-boundary and Unicode/CRLF annotations at320/390/1440px.
They check exact source selection/reconstruction, every code point's actual layout,
all annotation IDs by keyboard, retained tower focus, one tag per entity, no
tag/tag or tag/source collisions, exact bracket endpoints and catalog-wide colors.
The earlier scratch word range was corrected to `[0,14)` for adenocarcinoma.

[72 axe-core4.14.0 scans](security/v5.1-axe.jsonl) report zero automatic
WCAG-tagged violations. Color contrast remains incomplete in44 scans; manual
and assistive-technology review is still needed. All13 canonical palettes plus
the neutral fallback have static text/border contrast above4.5:1, recorded in
[entity-palette measurements](security/v5.1-entity-palette.json).

Ruff lint/format (95 Python files), static JS/CSS Prettier, generated EN/ES/CA
dictionary equality, original BSC SVG hash, Jinja compilation and git whitespace
checks pass. Bandit app/scripts has zero unsuppressed medium/high findings.
Wheel/sdist0.5.1 and no-NLP Docker build successfully; final wheel and running
container assets match repository bytes. Root and `/ner` container smoke checks
preserve private401/303 gates and minimal health; `/ner` completes real registration,
captured email verification, login/dashboard and logout/revocation. Local web/worker
run0.5.1. No BSC production deployment or clinical checkpoint validation is claimed.

See [OVERLAP_REVIEW.md](OVERLAP_REVIEW.md) for findings, before/after captures,
color mapping and remaining limits, and [OVERLAP_RENDERING.md](OVERLAP_RENDERING.md)
for implementation contracts. No scientific consolidation/export rule, schema
migration, authentication policy or72h retention change was introduced.
Earlier SMTP, TLS/BSC, legal, Torch and clinical/GPU limitations remain unchanged.

---

# Historical: V5 institutional interface (0.5.0)

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

## 0.7 retained quota, private normalization and sixteen UI languages

The CPU lock was resolved and installed with Torch 2.15.0+cpu, Transformers
5.22.1, FAISS CPU 1.15.1 and current compatible web/scientific dependencies.
Upstream ner_lab core remains pinned to commit
8640d4797b081a5f6b66d9b45c11269542a79a26; explicit inference dependencies replace
the older training extra's fixed Torch requirement.

Server regression: 194 passed, 80 browser-only cases skipped in that run.
The suite includes actual tiny local BERT inference/native ner_lab integration,
bi-encoder/FlatIP creation and disk reuse, Unicode offset round trips, English
fallback provenance, private Parquet import/ZIP escape rejection, three-language
LRU/72-hour expiry, atomic last-slot admission, deletion during inference,
repackaging without rerunning completed NER, retained-vs-lifetime counters,
filtering before pagination, ownership/CSRF and spawned stale-worker cancellation.
Catalog validation covers every source message and interpolation placeholder in
all 16 UI languages; document-language coverage is unchanged.

The existing design/overlap browser run passed 28 cases before the final SVG
font-scaling adjustment. The new 1440p/4K typography and 16-language navigation
checks passed for both root and /ner deployment paths. Final overlap checks also
exercise 4K and enlarged SVG geometry; see the final release validation below.
Ruff and formatting checks pass. Bandit reports no medium/high findings; pip-audit
finds no known vulnerabilities in core or the GPU scientific lock (the direct
ner_lab source URL cannot be audited as a PyPI version). Wheel build succeeds,
contains all 13 additional catalogs, and includes no Parquet/FAISS/gazetteers data.

Clinical accuracy was not evaluated. The provided private ZIP is 81,373,604 bytes;
Drive metadata was accessible, but binary download remained blocked in this
execution. Actual confidential dictionary schemas, clinical encoder weights,
full-dictionary RAM/disk needs and GPU throughput were not validated here. The
private local import/inspect commands and explicit schema flags are documented
in NORMALIZATION.md. All integration fixtures are synthetic, not clinical claims.

Final release validation: 16 overlap/browser cases passed, including all four
synthetic overlap corpora at 4K, preserving original source text, exact offsets,
centering, size ordering and click-only span lines. SVG fonts and geometry now
follow the root typography scale, and viewport changes redraw even when a capped
reading panel retains its width. The document manager passed two real-browser
cases (root and /ner), confirming erasure, quota refresh and unchanged lifetime
history. The 16 existing design cases also passed. Two additional cases validate
1440p/4K fonts and all 16 languages on login and authenticated document pages.
