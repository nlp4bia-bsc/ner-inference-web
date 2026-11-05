# Architecture and decisions

Browser → HTTPS reverse proxy → FastAPI → SQLite WAL + private local disk.
A separate worker claims the oldest queued sequence, invokes ner_lab per selected
checkpoint over the whole document mapping, validates/merges spans, computes
statistics and packages results. HTTP never runs inference; closing a browser has
no effect on a job.

SQLite is an intentional alternative to PostgreSQL + Redis + RQ, scoped to a
single Linux host. `BEGIN IMMEDIATE` makes rate-limit checks, both IP/email keys,
queue-capacity checks and job insertion atomic across web processes. FIFO order is
the database admission sequence, not upload start time. A worker lifetime flock
prevents two supervisors from processing at once. Database claims are atomic.
All inputs are renamed from staging before job insertion, so a committed job
always has input. A failed transaction removes its unregistered directory. A
process crash in that gap leaves an orphan removed by the periodic sweep.

States: QUEUED → PROCESSING → COMPLETED or FAILED → EXPIRED → deleted tombstone.
Every transition has an event timestamp; times are UTC epoch seconds internally
and ISO-8601 UTC in HTTP. Original relative paths identify documents unambiguously.
The payload records submitter metadata, language, entities, original paths and a
snapshot of model identity/digest/options. No document text is stored in SQLite.

On worker restart, interrupted jobs return to QUEUED at their original sequence,
up to MAX_ATTEMPTS (2 by default). A second interrupted attempt becomes FAILED.
Ordinary inference errors are terminal and require resubmission; repeated public
failures do not monopolize the queue. Each attempt builds in a private fresh
directory, then renames a complete output directory before committing COMPLETED.
If the supervisor dies, Linux parent-death signaling kills its inference child.
A per-job hard timeout terminates the child; heartbeat/retention continue while
inference runs. Lost completion commits are safe to replay from original input.

There are no partial successes: all selected models, statistics, required exports
and offset checks must pass. Completed document count is 0 until the entire batch
is published. No intermediate per-document progress is claimed by ner_lab's API.

Admission bounds actual request bytes before multipart parsing, including requests
without Content-Length. At most MAX_CONCURRENT_UPLOADS are buffered; each has a
five minute body timeout. Persistent leases expire after ten minutes after crashes.
A conservative reservation of `8 * MAX_UNCOMPRESSED_MB + MAX_UPLOAD_MB` per admitted
job/upload and disk free-space checks constrain total storage admission. This is
capacity planning, not a kernel disk quota: use a dedicated filesystem quota for
hard disk enforcement, especially model-generated intermediate amplification.
Model memory/CPU are bounded operationally by container resources and job timeout.

Cleanup runs periodically in both API and worker and can also run as a scheduled
command. COMPLETED/FAILED inputs, intermediates, outputs and metadata are removed
after their TTL. Download endpoints enforce expiry even before the next sweep.
An EXPIRED tombstone remains for TOMBSTONE_HOURS; after deletion the URL is 404.
The web app remains available without models; readiness separately reports that
fact. Worker and database must share local persistent storage.

English UI copy is contained in two templates and centralized JS message maps;
future localization can replace these sources without changing the model catalog.
Storage access has a Protocol seam, but transactional publish/delete semantics must
be implemented explicitly when replacing local storage with an object store.
