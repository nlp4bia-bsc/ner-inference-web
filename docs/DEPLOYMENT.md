# Deployment on a single Linux host

The web service and worker need shared private local storage (SQLite WAL/flock
must not use NFS), Python 3.12, and trusted checkpoints. Configure PUBLIC_BASE_URL
for the actual public HTTPS origin. The default assumes root mounting. To expose
`https://temu.bsc.es/ner/`, the proxy must consistently rewrite routes, static assets,
API and generated URLs; subpath mounting is not implemented in this version.
Prefer a dedicated root-mounted hostname/service until subpath support is added.

## Containers

`docker compose up --build -d` builds a no-model web image and starts web + idle
worker. Dependencies are pinned in requirements.lock. Real inference requires
`INSTALL_NLP=true docker compose build web`; requirements-nlp.lock pins the full
upstream NER extra, including Torch 2.10.0 and its large CUDA/training dependencies.
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

Example model preflight after editing catalog to paths under `/models`:

```sh
INSTALL_NLP=true docker compose build web
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/catalog:/service/catalog:rw" worker python -m scripts.validate_models
docker compose up -d --force-recreate
```

In a managed HTTPS proxy environment, build with the provided CA trust bundle:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  --build-arg INSTALL_NLP=false -t temu-ner-web:local .
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
checks web liveness; `/ready` checks worker heartbeat and reports model availability.
Alert separately on models_available=false when production expects checkpoints.

## Environment

All settings are listed in .env.example and app/config.py. Compose explicitly maps
them, so shell/.env values reach both containers. Important adjustments:

| Setting | Default / purpose |
|---|---|
| DEVICE, WORKER_CONCURRENCY | auto, 1 (other concurrency rejected) |
| MODEL_CONFIG_PATH / MODEL_VALIDATION_PATH | catalog YAML and private preflight receipt |
| STORAGE_ROOT / PUBLIC_BASE_URL | private local data / public origin |
| MAX_DOCUMENTS_PER_JOB | 1000 |
| MAX_UPLOAD_MB / MAX_UNCOMPRESSED_MB / MAX_DOCUMENT_MB | 50 / 250 / 5 MiB |
| MAX_ZIP_ENTRIES / MAX_COMPRESSION_RATIO | 5000 / 100 |
| RATE_LIMIT_SECONDS | 60, separately enforced for IP and email |
| MAX_QUEUE_SIZE / MAX_CONCURRENT_UPLOADS | 100 pending/active / 4 bounded uploads |
| MAX_STORAGE_MB / MIN_FREE_DISK_MB | 10000 reservation budget / 500 free floor |
| MAX_ATTEMPTS / JOB_TIMEOUT_SECONDS | 2 interruption attempts / 7200 seconds |
| JOB_RESULTS_TTL_HOURS | 24 from terminal completion, including failed jobs |
| CLEANUP_INTERVAL_SECONDS / TOMBSTONE_HOURS | 60 / 24 |

Storage reservation may reduce effective queue capacity below MAX_QUEUE_SIZE: the
minimum of queue and storage bounds wins. Use a dedicated disk quota for a hard
storage limit; model intermediate output can exceed the conservative reservation.
Provision CPU/RAM/GPU and disk after measuring maximum allowed corpora/model counts.
Single-host SQLite is unsuitable for horizontally distributed services.

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
resource limits, backup/privacy policy, monitoring and any GPU mounts. No SMTP or
external mail service is required. An optional future notifier can react to
COMPLETED events without changing capability-link retrieval; none is connected.
