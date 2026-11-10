# Administrator approval and project access review — 0.11.0

Reviewed 2026-11-10 during implementation. This is a developer review with
synthetic regression evidence, not an independent penetration test or certification.
Executed commands and results are recorded in [VERIFICATION](../VERIFICATION.md).

## Intentional policy change

The product owner explicitly requires administrator approval of new registrations,
inspection/erasure of all projects, account deletion, numeric per-user document
quotas and a distinct administrator theme. The original V4 owner-only policy for
ADMIN is superseded by this explicit cross-owner privilege. Ordinary users remain
owner-only. Clinical content is therefore visible to trusted administrators;
current privacy/terms text and UI ownership notices say so.

## Authorization and identity boundaries

- Registration explicitly inserts PENDING / USER / STANDARD and accepts only the
  profile schema. It cannot accept role, owner, approval or quota assignments.
- Login, session resolution and sensitive-write transaction revalidation require
  APPROVED / ACTIVE. Email verification does not grant administrator approval.
- Every administration route has a server dependency requiring active approved
  ADMIN plus an MFA-verified session. The same gate is used for foreign project
  routes in both early middleware and JobService. HTML links/theme grant no rights.
- Unknown/foreign project IDs remain 404 for ordinary users. Direct, encoded and
  query-manipulated URLs are covered by real-server tests, with and without /ner.
- CSRF, origin/Fetch Metadata checks, body bounds, no-store/no-referrer, CSP,
  SQL-bound values and escaped Jinja/DOM text remain in force. Administrative
  profile search includes IDs for following account-deletion audit requests.
- Reviews only accept PENDING. Role, suspension, quota, approval and deletion
  writes serialize under BEGIN IMMEDIATE and revalidate the current actor. Cached
  role/session state cannot complete a destructive write after lock-wait revocation.

## Erasure and races

Project erasure holds the same job lock as document publication, removes private
artifacts and replaces the job with a redacted DELETED tombstone. It releases
retained capacity and marks the owner's upload history removed. Tombstones fence
late worker completion. Account erasure commits DELETING / SUSPENDED and revokes
sessions before collecting projects, so admission cannot race in a fresh project.
It removes owned content, profile, ledger, session/action/MFA-setup records and
matching pending encrypted mail, keeping opaque audit identifiers. A partial
filesystem failure remains blocked for retry and cannot be reactivated via status.
Self-deletion and removal of the last active approved administrator are rejected.

Fresh quota checks occur after upload spooling inside the admission transaction.
Lowering the cap does not delete content. Custom zero, increases, decreases and
reset-to-tier have API/browser regression coverage, including quota changes while
an upload is blocked. Account deletion during upload is separately exercised.

## Migration and presentation

Migration6 runs transactionally/idempotently and marks existing accounts APPROVED.
It preserves actual old administrator credentials, MFA and sessions; new public
registrations explicitly opt into PENDING. Tests construct a genuine version5
schema and verify preservation, rollback on an injected DDL error and retry.
The admin-theme class is determined only by server-resolved role. Mauve styling
covers authenticated work views without overriding the NER category palette;
real-browser comparisons check matching entity colors for owner and administrator.

## Practical limits

A live read is authorized against the session at request entry; an already sent
response, screenshot or downloaded export cannot be recalled after revocation.
Filesystem unlink/SQLite deletion is not secure media wiping and does not alter
institutional backups. Operators still control trusted administrator enrollment,
TLS/proxy boundaries, storage permissions, protected backups and audit retention.
Optional SMTP delivery, real confidential terminology and biomedical model accuracy
are not established by these synthetic account/permission/UI tests. No model or
normalization algorithm changes are part of this release.
