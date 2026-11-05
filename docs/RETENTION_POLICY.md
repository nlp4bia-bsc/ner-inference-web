# Private 72-hour retention

JOB_RESULTS_TTL_HOURS defaults to 72 in Python, .env.example and Compose. For both
COMPLETED and FAILED jobs, expires_at = terminal completion + configured hours.
QUEUED/PROCESSING jobs have no expiry. Queue waiting time cannot consume download
time. A minimal expired tombstone remains for TOMBSTONE_HOURS (default 24), then
its events/row disappear. Tombstones are not document retention.

All content is private: originals, ANN, TSV, ZIP, native/operational statistics,
viewer index/per-document annotations and worker intermediates. The API's
JobService.available/completed guards are shared by status, downloads, statistics,
viewer HTML and every new document route. Exactly at expiry these return 410;
unknown/deleted capabilities return 404. No static mount exposes storage.

API and worker sweep periodically without browser visits. Removal deletes the
entire job directory (including viewer artifacts/locks) before scrubbing PII and
marking EXPIRED. Repeating cleanup is safe. Active jobs are excluded. Failed jobs
and unregistered staging artifacts follow the existing explicit cleanup policy.
If both processes stop, schedule `python -m scripts.cleanup`; deletion cannot run
while the host is down. Physical removal normally occurs within one sweep after
expiry; HTTP denial does not wait for the sweep.

Responses carry no-store/no-referrer/noindex. The frontend uses only memory/DOM,
clears loaded document data at expiry, and stores nothing in localStorage or
IndexedDB. User-downloaded artifacts cannot be revoked. SSD/SQLite/backup forensic
erasure requires encrypted storage and institutional policy; unlink is not a
secure media eraser. Do not archive temporary clinical data indefinitely.

Existing terminal jobs retain their recorded deadline unless the operator runs
`python -m scripts.migrate_retention` during a coordinated upgrade. It updates
still-unexpired COMPLETED/FAILED jobs to completed_at + configured TTL and never
revives an expired job. Queued jobs naturally use the new default when completed.
No database schema migration is required. Old v1 result packages can be indexed
lazily for the viewer while still valid, under a private per-job lock.

Tests use a controlled clock for 71-hour access, exact 72-hour denial across every
old/new private endpoint, complete artifact/PII removal, idempotent cleanup,
prolonged queue waiting and explicit retention migration. No real 72-hour sleep.
