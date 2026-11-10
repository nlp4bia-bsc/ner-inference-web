# Account, MFA and deployment recovery

> Current policy: email verification is optional (disabled by default). New access
> requests require administrator approval regardless of email verification. The
> SMTP guidance below applies only when those mail-based workflows are enabled.
> Existing administrator accounts/MFA survive migration6; see
> [Administration](ADMINISTRATION.md) for approval, quota and account erasure.

Use the public forgot/reset flow for a forgotten password. Its response is generic,
tokens expire after30min and are one-use. Reset revokes all sessions and requires a
new login; it does not remove MFA or prove email possession for another purpose.
Resend verification issues a fresh link and invalidates earlier unused links.
If SMTP is unavailable, processing by unverified accounts remains blocked. Repair
SMTP and resend; never mark users verified via an HTTP testing shortcut.

For a lost authenticator, use one of the eight saved one-use recovery codes in the
login OTP field. A consumed code cannot be reused. Codes are displayed only after
password-protected TOTP enrollment; their hashes and encrypted TOTP secret stay
private. Losing all factors requires an institutionally authorized, audited local
recovery procedure. There is deliberately no public MFA-reset/first-admin override.
A trusted operator with exclusive database access can reset MFA state and advance
auth_version/revoke sessions in one transaction, record an ADMIN_MFA_RECOVERY event,
and require re-enrollment before administrative access. Identity verification and
approval for this exceptional operation are institutional duties, not an email-only
fallback. Do not use arbitrary SQL through an exposed web/admin API.

For an upgrade, drain/stop both web and worker, take a temporary encrypted SQLite
backup using Connection.backup (including a consistent WAL state), and protect the
matching private rate-key. The key derives purpose-separated email/MFA encryption
keys; losing/replacing it makes stored secrets/outbox payloads unreadable. A database
backup contains sensitive account hashes and job metadata; its retention and access
must follow institutional policy. No automatic long-term clinical backup is added.

Startup runs additive migrations1–3. Migration3 adds users, hashed sessions/action
tokens, audit/abuse/MFA/outbox tables and a nullable indexed job owner. It does not
reset job sequence, rewrite documents/offsets or extend old deadlines. Tests upgrade
an actual b8d4d4f database copy, inject a mid-DDL failure, verify rollback, retry and
idempotence. Do not start a v3 worker concurrently with the coordinated migration.

After restoring a backup, revoke all stored sessions and action tokens and advance
users' authentication generations before opening traffic. This prevents restored
verifiers from reactivating sessions revoked since the snapshot. Sweep expired
jobs before exposing access; never revive an expired job to recover a user link.
Restore the matching key only through the protected secret/backup procedure.
A rollback after accepting v4-owned jobs must not restore a v3 public-capability
application: that would reopen anonymous access. Use a maintenance response or a
compatible authenticated release. Roll back data/code from a consistent snapshot
only with traffic stopped and the institutional retention policy applied.

Account suspension and role changes revoke sessions immediately. If an upload or
privileged mutation was already reading a body, it revalidates the live session
inside the write transaction. A body cannot resurrect a session after logout-all.
Already transmitted downloads/clipboard material cannot be recalled. Open-page
clearing is additional privacy hygiene; authorization is enforced by the server.

The application is single-host SQLite WAL/flock. Keep shared storage off NFS, keep
keys/volumes private and encrypted, use only trusted immutable model checkpoints,
and configure TLS/HSTS/proxy trust before production. No clinical/GPU deployment,
external penetration test, formal compliance certification or actual SMTP-provider
round trip is claimed by the local synthetic tests.
