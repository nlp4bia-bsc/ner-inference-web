# Private 72-hour retention

JOB_RESULTS_TTL_HOURS defaults to 72 in Python, .env.example and Compose. For both
COMPLETED, COMPLETED_WITH_ERRORS and FAILED jobs, expires_at = terminal completion + configured hours.
QUEUED/PROCESSING jobs have no expiry, including their early published documents. Queue waiting time cannot consume download
time. A minimal expired tombstone remains for TOMBSTONE_HOURS (default 24), then
its events/row disappear. Tombstones are not document retention.

All content is private: originals, ANN, TSV, ZIP, native/operational statistics,
viewer indexes, incremental published documents, incomplete microbatches and worker intermediates. The API's
JobService.available/completed guards are shared by status, downloads, statistics,
viewer HTML and every new document route. All these routes also require a live session and owner access or approved
ADMIN+MFA. Exactly at expiry authorized access receives410; ordinary users
receive404 for foreign/unowned locators;
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

V3 startup does not modify old deadlines. Versioned additive schema migrations are
separate from the optional explicit deadline-change command. The new progress
endpoint supplies server_now + expires_at; the shared UI counts down using elapsed
performance time after server synchronization, not an assumed browser wall clock.
The open viewer clears text, annotation table, inspector, selection and download
links on expiry. It never puts content in localStorage/IndexedDB. Browser tests
exercise clock skew and expiration with loaded data; API tests enforce actual TTL.

V4 account persistence does not extend job files or deadlines. Migration3 only
adds nullable ownership and account/security tables. Historical ownerless jobs
remain inaccessible to ordinary users and expire on schedule; email matching never transfers them.
Session cookies expire independently from job retention. Login again to read an
owned, still-valid result. Password reset/logout/suspension do not revive or
transfer results. Account/audit retention and protected backups are separate
institutional policies; see AUTHENTICATION_V4.md and RECOVERY_V4.md.

## 0.11 explicit administrative erasure

Administrator project deletion can occur before expiry or during processing. It
removes private artifacts and document/progress/event rows, releases the owner's
retained quota and marks lifetime upload metadata DELETED. A redacted DELETED job
tombstone with no owner/payload/result PII prevents late workers republishing data.
Account deletion first revokes access and blocks admission, then erases all owned
projects and the profile, ledger, sessions/action tokens and pending mail. Failed
filesystem erasure leaves the account blocked for retry. Opaque audit identifiers
remain; downloaded copies, backups and forensic media erasure are outside this
operation. See [Administration](ADMINISTRATION.md) and the draft privacy notice.
