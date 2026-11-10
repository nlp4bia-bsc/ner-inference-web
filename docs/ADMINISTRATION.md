# Administrator approval, projects and document quotas (0.11.1)

## Access requests

Public registration validates the profile, four-character minimum password and
unique normalized email, then stores a **PENDING** USER / STANDARD access request.
It issues no authenticated session. Pending and rejected users cannot sign in,
use private APIs or upload documents. Verifying an email, when explicitly enabled,
does not approve a request. By default registration neither sends mail nor requires
email verification. Approval is mandatory and has no public bypass/configuration flag.

An existing administrator signs in with email/password and opens **User management** (`/admin`).
Pending cards show full name, email, institution, professional activity and its
OTHER description. **Approve** enables subsequent login; **Decline** blocks it.
Reviews are transactional, audited and only accept PENDING requests. A second
review returns 409. Rejected requests remain visible; delete the rejected account
if the person must submit a new request with the same email. Approval is displayed
on the registration/login flow; no automatic approval email is sent.

The administration links and pale mauve workspace appear only for ADMIN accounts.
Every work page seen by an administrator uses that theme, including annotation and
the viewer. Entity category colors and shared overlap brackets are unchanged.
Theme/link visibility is presentation only: backend authorization is mandatory.

## All projects

**All projects** (`/admin/projects`) lists projects across owners with owner name,
email and institution, project name, language, status and document counts. Search
and pagination are server-side. Open job, viewer, document management and exports
use the ordinary project routes with the same expiry checks. Approved, active
ADMIN with a live session grants administrative access. MFA is disabled by default. Other users
remain strictly isolated, including direct and percent-encoded URLs. Merely knowing
a project ID or legacy link, or claiming a role in a form, grants no access.

Delete project removes its originals, annotations, exports and intermediate files,
including during processing. Its owner's retained-document quota is released.
The owner's lifetime upload history records the removal rather than disappearing.
A redacted DELETED job tombstone fences late workers; no document text, source
filename, payload, result metadata or owner ID is kept in that tombstone. The audit
retains opaque actor/target/job identifiers. Expired/ownerless legacy projects can
be listed and erased by administrators but are never reassigned by email.

Personal Dashboard, My jobs and unfiltered My documents remain personal. Use the
explicit All projects view to inspect other owners; document management identifies
the owner and does not display the administrator's personal quota as theirs.

## Per-user numeric quotas

In User management, **Document limit** accepts a whole number from 0 to 2147483647.
It overrides the selected tier's administrative cap. Empty restores the tier
default (STANDARD 100, EXTENDED 1000, UNLIMITED no administrative cap).

The display is **occupied / limit**, counting documents retained across all jobs.
User/system deletion or expiry frees capacity; historical upload counts do not
consume quota. Increasing a limit allows more uploads immediately. Decreasing
below current occupancy keeps every existing document and blocks further uploads
until there is enough capacity. Zero blocks all new documents. The technical
`MAX_DOCUMENTS_PER_JOB` ceiling, if set, still applies independently.

The browser displays the current value, but the admission transaction reads the
fresh database limit and session state again after receiving an upload. A quota
change, suspension or deletion during a long upload cannot be bypassed by keeping
the page open. Tier changes leave an explicit numeric override in place until it
is cleared. Limit/tier changes are audited and do not invalidate sessions by themselves.

## Account deletion

**Delete account** asks for confirmation naming the selected email. It removes the
profile, all owned projects/documents/exports, upload ledger, sessions, verification,
reset and MFA-setup records, and matching pending encrypted email messages. Shared
model caches, terminology resources and other owners' data remain available.
Deletion is not secure media wiping and does not erase institution-managed backups
or downloaded copies. Opaque audit identifiers remain under audit retention.

The target is first committed as DELETING / SUSPENDED and all sessions are revoked.
Only then are its projects erased under their locks. Fresh admission is blocked.
A filesystem error leaves the account blocked in Deletion in progress; retry the
same deletion to complete it. The account cannot be reactivated by changing status.
Administrators cannot delete themselves, and the last active approved administrator
cannot be demoted, suspended or deleted. Role/state writes and destructive actions
revalidate the actor inside their SQL transaction, including after waiting on a lock.

A user's existing **Request account deletion** action remains an audited request;
it does not delete automatically. The administrator can follow its target ID from
the audit list to the account and complete the deletion.

## Upgrade an existing installation

Migration 6 is additive, transactional and idempotent. It sets **existing accounts
(including the existing administrator) to APPROVED**, adds approval-review fields
and a nullable document quota override. Existing credentials, MFA secrets and
sessions are preserved. Only new public registrations default to PENDING.

Stop web and worker together, protect a consistent private database/key backup,
pull this branch and restart both from the same checkout/environment. Database
initialization applies the migration automatically. In Conda use `python3` from
the activated environment for both processes; no new shell exports are required.
Keep the existing `.env`, private `storage/` and `gazetteers/`.

For Docker, rebuild/recreate web and worker using the existing deployment profiles;
see [Docker quickstart](DOCKER_QUICKSTART.md). No new environment flag or SMTP setup
is needed. **Do not run create_admin again if the administrator already exists.**
MFA is not required and its setup links/endpoints are disabled by default, even
for previously enrolled accounts. New installations bootstrap once through the trusted interactive
`python3 -m scripts.create_admin` command, never a public first-user privilege rule.

See [API](API.md), [route inventory](ROUTE_SECURITY_V4.md),
[review and limitations](security/admin-approval-review.md) and
[executed verification](VERIFICATION.md).

## MFA policy (0.11.1)

`ENABLE_MFA=false` is the Python and Compose default. Sign-in uses email/password;
previously enrolled accounts also bypass the second factor. Approval, ACTIVE state,
ADMIN role, live-session revalidation, CSRF/origin checks and revocation still apply.
Login has no OTP input, profile/navigation have no MFA links, and `/mfa` plus its
HTML/API enrollment actions return404. No new migration or enrollment is needed.
Stored encrypted secrets/recovery hashes are preserved rather than erased. Only
an explicit future `ENABLE_MFA=true` enables the original enrollment and MFA rules.
Password-only sessions are never marked MFA-verified: after enabling, administrators
must sign in with the second factor before using administrative features.
