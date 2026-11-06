# Deployment on a single Linux host

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

## Containers

`docker compose up --build -d` builds separate web and worker images. Web installs
the HTTP dependencies; worker installs the pinned CPU inference libraries by
default (`INSTALL_NLP=true`, `NLP_PROFILE=cpu`). No model weights are downloaded
during image build or application startup. `requirements-cpu.lock` selects Torch
2.10.0+cpu without CUDA runtime packages; the GPU profile is opt-in.
Allow sufficient build disk/network capacity. Production model initialization and
GPU drivers must be validated on BSC; the Compose file does not request GPUs.
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
resource limits, backup/privacy policy, monitoring and any GPU mounts. Production now requires configured STARTTLS SMTP for account verification/recovery,
HTTPS/Secure cookies and administrator MFA. The local file-mail example is for
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
HTTPS origin/prefix, Secure cookies and SMTP, then deploy together. Migration3 is
additive; old ownerless links are closed without changing their TTL. Do not claim
historical jobs by email, and do not expose a v3 rollback against the v4 database.
The web container alone receives SMTP credentials. Bootstrap with
`docker compose exec web python -m scripts.create_admin` in an interactive terminal,
verify mail, enroll TOTP and save recovery codes before administering accounts.

The full native CPU regression uses a synthetic checkpoint. Clinical checkpoints,
GPU/full-neural images and real SMTP/BSC edge delivery have not been validated.
The upstream torch2.10.0 pin retains two published advisories; resolve the neural
profile risk before declaring that deployment hardened. HTTP dependency/security
results are recorded separately in SECURITY_AUDIT_V4.md.
