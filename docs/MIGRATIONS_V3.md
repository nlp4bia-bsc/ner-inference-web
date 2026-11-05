# SQLite migrations and upgrade / rollback

Back up configuration and SQLite consistently with its backup API, respecting
retention. Drain/stop API and worker before upgrading together. Do not run the v2
worker against newly admitted v3 jobs. Startup runs additive migrations once,
serialized by SQLite transactions:

- Version 1: document states/metadata table and index; job stage/update time and
  byte-accounting fields; upload reservations. Existing jobs are reconciled once
  from disk during migration, never during HTTP admission.
- Version 2: upload staging ownership, so periodic orphan cleanup cannot remove
  an active upload's staging directory. Admission heartbeats refresh long validation
  leases. Anonymous body spools are closed/unlinked on success, failure or timeout.

schema_migrations records applied versions/times. Existing job IDs, token hashes,
payloads, terminal status and recorded expires_at are not rewritten. V1/v2 completed
jobs without document rows keep the legacy viewer/backfill path. Pre-v3 queued
jobs initialize PENDING document references when the new worker processes them.
Only new terminal completions use the configured TTL (default 72 hours).

The older optional scripts.migrate_retention command is not run by v3 startup;
it remains an explicit administrative deadline change, not part of this upgrade.

New job statuses extend the API with COMPLETED_WITH_ERRORS. Existing fields and
routes remain; progress and source metadata are additive. Clients should handle
new terminal statuses and distinguish partial attachments/manifests.

Rollback: stop/drain v3 components and restore the pre-upgrade code + consistent
pre-upgrade database snapshot if returning to v2. Retain/destroy the corresponding
private volume according to policy; never restore expired clinical data to public
access. An old worker cannot interpret partial v3 publications/states, so rollback
is not performed by dropping tables or rewriting live job states. New v3 jobs
cannot be transparently continued by v2. Prefer a forward fix once v3 jobs exist.

Tests upgrade an actual schema produced by baseline 9c95bb5 and verify old tokens,
status and exact deadlines survive, then run startup again idempotently.
