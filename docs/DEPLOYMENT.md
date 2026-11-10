# Deployment on a single Linux host

For the step-by-step Docker setup for https://temu.bsc.es:18443 (CPU/NVIDIA GPU, private Parquet import,
port forwarding, HTTPS and optional Conda data migration), see
[Docker quickstart](DOCKER_QUICKSTART.md).

Registration defaults to `REQUIRE_EMAIL_VERIFICATION=false` since0.5.4 and works
with `MAIL_BACKEND=none`; passwords have a four-character minimum. Accounts still
need a unique normalized email. `SUPPORT_EMAIL=fernando.gallego@bsc.es` is the
account/error contact, exposed as a mail-client link. SMTP is optional for
password recovery or automatic mail integrations, not an admission requirement.
Set `REQUIRE_EMAIL_VERIFICATION=true` only to explicitly enable the older policy.

The web service and worker need shared private local storage (SQLite WAL/flock
must not use NFS), Python 3.12, and trusted checkpoints. Configure PUBLIC_BASE_URL
for the actual public HTTPS origin and APP_PREFIX=/ner for the intended route.
Set PUBLIC_BASE_URL=https://temu.bsc.es/ner and preserve /ner in upstream requests
(no trailing slash on Nginx proxy_pass). All templates/static/API links are
prefix-aware. See README's complete /ner/ Nginx example. Prefix behavior is tested
locally; BSC TLS/domain deployment has not been performed.

## Native Python and remote port forwarding

Run these steps on the machine hosting Uvicorn and the worker, from the checkout
root and the same Python environment. Updating a different checkout or recreating
containers elsewhere does not update this process. Stop both old processes before
starting replacements. Use `python3 -m uvicorn` so the web server uses the active
Python environment rather than a different `uvicorn` executable on PATH.

`PUBLIC_BASE_URL` describes the address visible in the **browser**. If a remote
port is forwarded to `http://127.0.0.1:8000` on the browser's machine, use that
origin; the remote hostname is not the browser origin. A different forwarded
port or HTTPS scheme requires its own matching setting. Local mode also accepts
the `localhost`/`127.0.0.1` pair on that same scheme/port, as described below. Keep the
remote Uvicorn bound to loopback for a tunnel. This HTTP/local-cookie setup is
for loopback/tunneled development; public deployment retains HTTPS/Secure cookies.

Pydantic's precedence is explicit constructor values, **process environment**,
the `.env` in the working directory, then defaults. `git pull` does not update a
private `.env`, and copying `.env.example` cannot override an old shell export,
Conda activation variable or service-manager environment. A log still showing
`configured_origin=https://localhost:8000` means the running process has not
adopted the expected `http://127.0.0.1:8000` value. Check it in **each terminal**:

```sh
python -m scripts.check_config --expect-origin http://127.0.0.1:8000
```

The report shows each safe effective setting's source (`environment`, `.env` or
`default`), the absolute configuration/application/interpreter paths, and installed
inference modules without importing models or making network requests. It excludes
SMTP passwords, Hub tokens, cookies and patient data. Origin mismatch exits 1.
The comparison uses the same local-alias policy as the HTTP middleware.
`REQUIRE_EMAIL_VERIFICATION` should be false; its default is false. Correct any old
variables in shell startup/Conda/service configuration for a permanent fix.

To override stale values explicitly for the local forwarded origin, execute the
following in **both terminals** before launching their respective process:

```sh
export APP_ENV=development COOKIE_SECURE=false
export PUBLIC_BASE_URL=http://127.0.0.1:8000
export REQUIRE_EMAIL_VERIFICATION=false MAIL_BACKEND=none
export MODEL_LOADING_MODE=on_demand HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0
python -m scripts.check_config --expect-origin http://127.0.0.1:8000
```

In terminal 1:

```sh
python -m uvicorn app.asgi:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

In terminal 2:

```sh
python -m app.worker
```

Open the matching browser address, sign in again after a cookie-policy change,
and submit. There is no database migration or account re-verification for this
fix. Do not erase the storage directory; startup initializes schema idempotently.
The workspace banner is hidden when verification is disabled, including for
accounts with no `email_verified_at` value.

`requirements.lock` installs HTTP dependencies only. If the diagnostic reports
missing inference modules, install the actual worker profile in that same Python
environment: `python -m pip install -r requirements-cpu.lock` for CPU, or the
deployment's CUDA-compatible `requirements-nlp.lock` profile for GPU. This installs
libraries, not model weights; weights are downloaded/cached on first use. Test
execution and manual database initialization are not required for every update.

### Local aliases, cookies and inference dependencies

With `APP_ENV=development` (or test) and `COOKIE_SECURE=false`, a configured
`http://127.0.0.1:8000` accepts requests originating at both that address and
`http://localhost:8000`. The reverse configuration also works. Scheme and port
must stay equal; arbitrary domains, other loopback IPs and `0.0.0.0` are not
aliases. Production and Secure-cookie configurations retain a single configured
origin. CSRF proofs remain mandatory, and cross-site Fetch Metadata stays blocked.

Listening on `0.0.0.0` exposes network interfaces; it does not make browser origins
interchangeable. A forwarded loopback setup can keep `--host 127.0.0.1`. Browsers
isolate cookies between `localhost` and `127.0.0.1`, so switching hosts requires
sign-in on that host. Submission links preserve the validated local request host
instead of switching to the other alias; unrelated Host/forwarding values cannot
choose the returned private origin. Production retains its canonical configured URL.

An empty/missing `.env` is permitted when all settings come from the process
environment, but those exports must be supplied to each service on every restart
or kept in its launch configuration. Use `python3` consistently when `python` is
an old alias/function pointing at an unavailable Python 3.10. No Python 3.10
installation is needed for this project (Python 3.12 is recommended).

`inference_dependencies` must report all four modules present in the actual
worker environment. Install its profile once with the working interpreter:

```sh
python3 -m pip install -r requirements-cpu.lock
python3 -m scripts.check_config --expect-origin http://127.0.0.1:8000
python3 -m app.worker
```

Use the CUDA-compatible `requirements-nlp.lock` profile instead for GPU. These
are runtime libraries, not model weights. An incompletely provisioned worker now
exits before touching storage or claiming/recovering jobs, naming the missing
modules and installation command. Web can remain lightweight. If a dependency
fails later during a model invocation, safe model logs also identify a missing
top-level inference module. Fixing dependencies does not rerun a job already
marked FAILED; submit it again to produce a new audited job.

## Containers

For local browser use, run `docker compose up --build -d` and open
**http://127.0.0.1:8000**. The example and Compose defaults set `APP_ENV=development`,
`COOKIE_SECURE=false`, `PUBLIC_BASE_URL=http://127.0.0.1:8000` and `MAIL_BACKEND=none`.
Since 0.8 the Compose defaults also use this local HTTP configuration, so no
environment file or shell exports are needed for loopback use. Existing `.env`
files and exported values still override those defaults; review stale settings.
The local alias pair above accepts
`localhost` and `127.0.0.1`; scheme, port and configured prefix must match.

For an existing deployment, update those settings in its private environment and
recreate web and worker (`docker compose up -d --force-recreate`). Restart does not
apply changed environment values. Keep the data volume. When switching between
Secure production cookies and local development cookies, sign in again.
For production, retain Secure cookies/HTTPS and set the real public origin;
do not relax CSRF checks or trust arbitrary forwarding headers to fix a mismatch.

Origin rejection now returns a service-address configuration message instead of
suggesting a reload. The private `temu.auth` log records
`csrf_rejected reason=origin_mismatch configured_origin=... request_origin=...
referer_origin=... fetch_site=... check=PUBLIC_BASE_URL`;
it does not log the submitted ZIP, patient text, cookies or CSRF proof. A rejected
submission clears the upload progress while preserving selected files/models.

`docker compose up --build -d` builds separate web and worker images. Web installs
the HTTP dependencies; worker installs the pinned CPU inference libraries by
default (`INSTALL_NLP=true`, `NLP_PROFILE=cpu`). No model weights are downloaded
during image build or application startup. `requirements-cpu.lock` selects Torch
2.15.0+cpu without CUDA runtime packages; the GPU profile is opt-in.
Allow sufficient build disk/network capacity. Production model initialization and
GPU drivers must be validated on BSC; the base Compose file does not request GPUs. The optional GPU overlay in the
[Docker quickstart](DOCKER_QUICKSTART.md) supplies the device grant and GPU build profile.
To use GPU hardware add the site's supported NVIDIA runtime/device grant and size
memory; DEVICE=cuda alone does not grant a GPU.

Host `catalog` and checkpoints are mounted read-only. Data uses a named volume
initialized with UID 10001 ownership. Web/worker run as that non-root UID. Web is
limited to 1 GiB, worker to 8 GiB in the example; tune these to model/resource needs.
The supervisor uses a subprocess per job, so memory is released after each job.
init/restart policies and Linux parent-death signaling avoid orphan inference.
Do not scale workers; a second supervisor exits while the lifetime lock is held.

`MODEL_LOADING_MODE=on_demand` and online Hub access are the defaults. The first
job downloads its selected repositories to `/data/model-cache/hub`, shared via
the private `ner-data` volume. Warm jobs reuse the cache. `HF_TOKEN`, if needed
for gated/private repositories, is supplied only to the worker. Keep it in a
private environment/secret, not the catalog or Git. See [ON_DEMAND_MODELS.md](ON_DEMAND_MODELS.md).

Optional legacy preflight, only with `MODEL_LOADING_MODE=validated_local`:

```sh
NLP_PROFILE=cpu INSTALL_NLP=true docker compose build worker
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/catalog:/service/catalog:rw" worker python -m scripts.validate_models
docker compose up -d --force-recreate
```

In a managed HTTPS proxy environment, build with the provided CA trust bundle:

```sh
docker build --target web --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t temu-ner-web:local .
docker build --target worker --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t temu-ner-worker:local .
```

The optional BuildKit secret is consumed by pip only during the networked build
step and is not copied into image layers. Preserve existing proxy configuration
and TLS verification. Ordinary Docker installations need no CA secret. Image base
is Python 3.12-slim; dependencies/ner_lab revision are pinned, but OS/base tag and
build tools are not immutable. Pin the base digest in the deployment release for
fully immutable builds.

## HTTPS and client IP

Default Uvicorn uses --no-proxy-headers: it ignores spoofed X-Forwarded-For. Behind
a proxy, that conservative default limits all users sharing the proxy IP. To apply
per-client IP rate limiting, configure the proxy to overwrite X-Forwarded-For with
its directly observed client IP, block direct API access, and run Uvicorn with
`--proxy-headers --forwarded-allow-ips=<exact trusted proxy IP/CIDR>`. Never use `*`
on an internet-accessible backend. Multiple proxy hops require an audited trust
chain. The application reads ASGI request.client only, never raw forwarding headers.

Terminate TLS at BSC's proxy, enable HSTS there, set upload body bound to 51 MiB
(50 MiB payload + multipart allowance), timeouts to cover bounded uploads, and
upstream timeouts for downloads. Example location excerpt:

```nginx
location / {
    client_max_body_size 51m;
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    access_log off;
}
```

Do not log capability paths or query strings in reverse proxies/APM. `/health`
checks web liveness; `/ready` checks the worker heartbeat with minimal status; model catalog/metrics
require authentication. Check configured/cache states through an authenticated
catalog request. Offline preflight is optional in validated-local mode.

## Environment

All settings are listed in .env.example and app/config.py. Compose explicitly maps
them, so shell/.env values reach both containers. Important adjustments:

| Setting | Default / purpose |
|---|---|
| DEVICE, WORKER_CONCURRENCY | auto, 1 (other concurrency rejected) |
| MODEL_CONFIG_PATH / MODEL_VALIDATION_PATH | catalog YAML and private preflight receipt |
| MODEL_LOADING_MODE / MODEL_CACHE_DIR | on_demand / persistent Hub cache path |
| HF_HUB_OFFLINE / HF_TOKEN | false / optional private worker credential for gated models |
| STORAGE_ROOT / PUBLIC_BASE_URL | private local data / public origin |
| MAX_DOCUMENTS_PER_JOB | optional technical cap; per-account tiers are100/1000/null |
| MAX_UPLOAD_MB / MAX_UNCOMPRESSED_MB / MAX_DOCUMENT_MB | 50 / 250 / 5 MiB |
| MAX_ZIP_ENTRIES / MAX_COMPRESSION_RATIO | 5000 / 100 |
| RATE_LIMIT_SECONDS | 60, separately enforced for IP and email |
| MAX_QUEUE_SIZE / MAX_CONCURRENT_UPLOADS | 100 pending/active / 4 bounded uploads |
| MAX_STORAGE_MB / MIN_FREE_DISK_MB | 10000 reservation budget / 500 free floor |
| MAX_ATTEMPTS / JOB_TIMEOUT_SECONDS | 2 interruption attempts / 7200 seconds |
| JOB_RESULTS_TTL_HOURS | 72 from terminal completion, including failed jobs |
| CLEANUP_INTERVAL_SECONDS / TOMBSTONE_HOURS | 60 / 24 |

Storage admission combines persisted actual bytes, a configurable active-output
reserve (input bytes * STORAGE_RESERVE_FACTOR + STORAGE_RESERVE_EXTRA_MB), free
space and queue/upload bounds. It no longer walks completed directories inside
admission transactions. Expanded upload reservations grow before writes; private
staging ownership/heartbeats prevent cleanup races. Per-job output writers check
conservative budgets, while a real filesystem quota remains the hard disk limit.

INFERENCE_DOCUMENT_BATCH_SIZE=32 bounds source-document batches independently of
model window batch_size. MAX_LOADED_MODELS=2 bounds native checkpoint sessions.
Tune these after real CPU/GPU measurements. Clinical checkpoints, full NLP Docker
profiles and production/GPU load were not validated here; native tiny-BERT CPU
mechanics and the no-NLP image have been exercised.

## Retention and recovery

API and worker independently sweep retention. Also schedule
`python -m scripts.cleanup` with the same configuration if both are stopped for
maintenance; no process can clean while the host is down. Results become
undownloadable exactly at expiry, physical deletion normally within one sweep.
Deletion scrubs name/email/model payload and summary from live rows; tombstones and
events disappear after another day. Failed/unregistered staging artifacts expire
too. Backups must honor the institution's retention policy separately. SQLite
secure_delete and filesystem unlink do not guarantee physical erasure on SSDs;
use encrypted private volumes and controlled backups for sensitive material.

Checkpoint rollout: drain queue, stop worker, back up SQLite consistently with its
backup API, stage/validate immutable model directories, restart web+worker, check
/ready and smoke-test with authorized non-sensitive data. On worker crash,
interrupted jobs replay at their original FIFO sequence up to MAX_ATTEMPTS.
Inference exceptions/timeouts fail terminally without partial downloads.

The site still requires BSC domain/TLS/reverse proxy, checkpoint paths/revisions,
resource limits, backup/privacy policy, monitoring and any GPU mounts. Production requires HTTPS/Secure cookies and administrator MFA. STARTTLS SMTP
is needed only if email recovery or explicit email verification is enabled. The local file-mail example is for
loopback development only. See AUTHENTICATION_V4.md for exact settings/bootstrap
and RECOVERY_V4.md for coordinated upgrade/restore and MFA recovery.

Phase 2 upgrades and old-job deadlines: see [retention](RETENTION_POLICY.md).

V3 rollout: stop/drain both API and worker, back up SQLite consistently according
to retention policy, deploy together and let versioned additive migrations run.
Do not automatically run migrate_retention: old deadlines must remain unchanged.
See MIGRATIONS_V3.md. COMPLETED_WITH_ERRORS allows explicitly partial batch exports;
FAILED jobs may retain individual valid published documents. Both expire from
terminal completion. Live publication and recovery are in INCREMENTAL_PROCESSING.md.

## V4 rollout

Drain/stop both services, protect a consistent SQLite/key backup, configure the
HTTPS origin/prefix and Secure cookies, then deploy together. SMTP is optional
unless mail-based verification/recovery is enabled. Migration3 is
additive; old ownerless links are closed without changing their TTL. Do not claim
historical jobs by email, and do not expose a v3 rollback against the v4 database.
The web container alone receives SMTP credentials. Bootstrap with
`docker compose exec web python -m scripts.create_admin` in an interactive terminal,
enroll TOTP and save recovery codes before administering accounts. Verify mail
only if the optional email verification policy has been enabled.

The full native CPU regression uses a synthetic checkpoint. Clinical checkpoints,
GPU/full-neural images and real SMTP/BSC edge delivery have not been validated.
The torch2.10.0 advisory findings in SECURITY_AUDIT_V4.md describe the historical
V4 neural profile. Current CPU/neural locks use torch2.15.0; see VERIFICATION.md
for recorded current dependency/security results and their scope.

## Updating to 0.7 in Conda

Stop the existing web and worker processes first, then run in the checkout root:

```bash
conda activate ner-inference-web
git pull --ff-only
python3 -m pip install --upgrade -r requirements-cpu.lock
python3 -m pip install --no-deps -e .
python3 -m scripts.check_config --expect-origin http://127.0.0.1:8000
```

Use `requirements-nlp.lock` instead for the GPU Torch distribution. FAISS indices
remain portable CPU FlatIP; encoder execution follows DEVICE. The inference
profile installs current compatible runtime dependencies explicitly with ner_lab
core, avoiding the upstream training extra's fixed older Torch version. No
precompilation, model preflight or database reset is necessary. Schema migrations
run idempotently on startup; they retain existing accounts and jobs. Avoid
`cp .env.example .env` over a configured deployment: merge the new settings.
Keep PUBLIC_BASE_URL, cookie settings and inference profile consistent in both
terminals; shell exports in one terminal do not configure another terminal.

Confidential gazetteers belong in `./gazetteers/`, inside the repository root and
ignored by Git. See [NORMALIZATION.md](NORMALIZATION.md) for import commands.
Then restart web (`python3 -m uvicorn app.asgi:app --host 127.0.0.1 --port 8000
--no-access-log --no-proxy-headers`) and worker (`python3 -m app.worker`) in the
same Conda environment and with the same settings/storage.

## Retained-document quota and deletion

The quota is occupied / limit across **all jobs**: standard 100, extended 1000,
unlimited without a document cap. Deletion and expiry free slots. Admission
checks the freshest access tier and retained count inside the SQLite write
transaction, preventing simultaneous requests from claiming the same slot.

My documents lists private upload metadata even after document deletion/expiry.
Users may erase a document while queued, processing, failed or completed. This
removes its original, annotations and derived downloads, interrupts stale worker
content, and regenerates retained downloads without rerunning completed NER.
The original retention deadline does not extend. The lifetime upload ledger
retains metadata (filename, size, language, upload/removal time), never deleted
clinical text. Include this metadata retention in institutional privacy notices.
Files already downloaded to a user's own machine cannot be erased remotely.


## 0.8: persistent local configuration and queue diagnostics

For native Conda execution, keep both processes, from the same checkout root.
Persist these lines in the existing private `.env` **once**, merging rather than
replacing its storage/model paths. Remove conflicting old shell/Conda variables:

```dotenv
APP_ENV=development
COOKIE_SECURE=false
PUBLIC_BASE_URL=http://127.0.0.1:8000
REQUIRE_EMAIL_VERIFICATION=false
MAIL_BACKEND=none
MODEL_LOADING_MODE=on_demand
HF_HUB_OFFLINE=0
TRANSFORMERS_OFFLINE=0
```

Then launch in two terminals with `conda activate ner-inference-web`:

```sh
# Terminal 1, from the repository root:
python3 -m uvicorn app.asgi:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
# Terminal 2, from the same root, same Conda environment:
python3 -m app.worker
```

`python3 -m scripts.check_config --expect-origin http://127.0.0.1:8000` now reports
`processing_service`: absolute database path, existence, heartbeat age and
`idle`/`busy`/`unavailable`. It reads an existing database without creating one.
Compare the database paths in `web_ready` and `worker_ready` logs. Different
working directories, storage settings, interpreters or Conda environments can
otherwise run two valid processes against different queues. `worker_ready`
explicitly means it is waiting for jobs. Each accepted/started/finished project
and model phase is logged; logs omit clinical text and exception strings.

A heartbeat older than 15 seconds is unavailable. A queued project cannot yet be
building its FAISS index: the worker first claims it, changing it to PROCESSING.
The UI shows unavailable processing service or a busy worker, then per-model
loading, native inference-window counts and normalization/index phases. Downloads
and initialization show indeterminate progress; no elapsed-time ETA is invented.
Expanded model details scroll with the page; the compact active summary can stay
sticky. Terminal summaries no longer cover document controls in the viewer.
The model inference percentage excludes normalization. The separate published
annotation count still means documents with validated results on disk.

For Docker, `docker compose up --build -d` starts both services with shared storage
and the local defaults above. No exports or model precompilation are required.
Use `--force-recreate` after changing environment configuration; keep the volume.
For public HTTPS deployments explicitly set `APP_ENV=production`,
`COOKIE_SECURE=true` and the real HTTPS `PUBLIC_BASE_URL`, with the documented
reverse proxy/TLS setup. Production validation has not been relaxed.

The additive schema migration 5 stores per-model counters and generation guards.
Restart web and worker together after updating; do not reset accounts or storage.
Project deletion is available on Dashboard/My jobs, while My documents retains
individual deletion and adds bulk deletion. A project-scoped manager deletes
that project's documents; the unfiltered manager deletes across the account.
Confirmations state the scope. Neither action clears lifetime upload metadata.


## 0.8.1 terminology import and selected deletion

No new dependencies or database migration are required. Update the checkout,
import the private ZIP as described in [NORMALIZATION.md](NORMALIZATION.md), and
restart both Conda processes. The configuration diagnostic now reports terminology
registration separately from the worker heartbeat. `--inspect` alone is not an
import. Previously completed partial jobs require a new submission to normalize.
My documents supports per-page selection and selection across pages, then one
confirmed Delete action. Retained quota refreshes; lifetime upload metadata stays.


## 0.9 lexical normalization and DT4H reimport

Existing Conda deployments can install `rapidfuzz==3.14.6` without replacing
their Torch CPU/GPU profile. Reimport the private ZIP with path-driven language
grouping, restart both Python3 processes, and submit a new job. See the full
[update commands and privacy details](NORMALIZATION.md#fast-parquet-matching-and-corrected-language-grouping-09).
No terminology database or new shell exports are required. Docker installs the
updated lock profile and retains the existing private gazetteer/cache mounts.


## 0.10 phased publications and timeout diagnosis

Stop/drain the old worker, update the checkout and restart both Conda Python3
processes (or rebuild/restart both Compose services). No new dependencies or
manual database migration are required. New jobs publish model/category previews;
old failed jobs without saved annotations need a new submission. Existing final
publications remain readable. My documents deletion controls are unchanged.

`JOB_TIMEOUT_SECONDS` remains 7200 by default, covering the entire child lifetime,
including cold bi-encoder/FAISS builds. A timeout now logs `reason=JobTimeout`,
`timeout_seconds` and the child exit code, and records the timeout on unfinished
model cards. Completed NER/normalization snapshots remain individually readable.
To allow a longer intentional bi-encoder job, set a suitable whole-job deadline
in the shared private `.env` and restart the worker. Fast lexical normalization
remains the default when normalization is enabled. Do not infer a timeout solely
from an old `WorkerInterrupted` or `success=False` message.

## Updating to 0.11: approval and administrator management

Stop web and worker together, keep a consistent private SQLite/key backup, pull
and restart both from the same version. Initialization runs additive migration6
transactionally; no manual SQL is needed. Existing users/admins are APPROVED, and
passwords, MFA and sessions are preserved. Only new public access requests become
PENDING. Do not recreate the existing administrator or overwrite `.env`.

For Conda, activate the same environment and use `python3 -m uvicorn app.asgi:app`
with your existing host/port options and, in the other terminal,
`python3 -m app.worker`. For Compose, rebuild/recreate web and worker while keeping
the persistent volume and private gazetteer mount. No new environment variable or
SMTP requirement is introduced. See the [Docker quickstart](DOCKER_QUICKSTART.md)
for the complete profiles and [Administration](ADMINISTRATION.md) for workflows.

`/admin` now approves/declines access, manages numeric per-user document quotas,
and deletes accounts with their data. `/admin/projects` explicitly lists all owners'
projects for inspection/erasure. Both require ADMIN plus live MFA. All administrator
views have a pale mauve theme, preserving entity colors. The privacy notice and
route matrix describe this intentional cross-owner administrative access; older
V4 audit reports describe the previous owner-only policy.
