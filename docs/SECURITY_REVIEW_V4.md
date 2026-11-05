# Independent V4 security review

Reviewed on 2026-11-05 by a separate review agent, independently of the implementation
agent. Scope: the V4 working tree based on `b8d4d4f`, including authentication,
account/profile schemas, sessions, tokens/email, MFA, authorization policies,
admin routes/services, job admission/ownership, migrations, legacy HTTP aliases,
configuration and relevant browser clients. This is a source review with focused
executable probes, not a certification or an external penetration test.

## Findings and corrections

| ID | Initial finding | Risk | Correction and independent recheck |
|---|---|---|---|
| R1 | First-admin bootstrap called duplicate-tolerant registration, then promoted the account found by email. An existing account retained its original password instead of the operator's newly entered password. | High | Bootstrap now requires a new email and creates the ADMIN identity atomically. A duplicate-email reproduction initially promoted the existing account; repeating it after correction raises a safe error. The first email-verification token also keeps the correct account generation. |
| R2 | Reset consumption ran Argon2id before rejecting a random recovery token, with no consumption throttling. | High, resource exhaustion | The endpoint throttles consumption; token eligibility is checked before hashing, then checked again under the write transaction. An invalid 43-character token initially called the password hasher once; after correction it calls it zero times. |
| R3 | A previously resolved principal could rotate a session after logout-all and obtain a new valid session. | High | Logout-all advances the account authentication generation. Rotation revalidates the original live session inside BEGIN IMMEDIATE. The original reproduction initially resurrected a valid session; the corrected operation returns 401. |
| R4 | Privileges were resolved before request-body receipt, with a timeout per chunk. A delayed request could carry an old ADMIN principal past suspension/revocation. | High | A total deadline bounds small request bodies, the middleware re-resolves the session afterward, and sensitive account/admin mutations and job admission revalidate the session transactionally. A real authenticated MFA administrator's cached principal cannot mutate accounts after logout-all: the independent service probe returned 401. |
| R5 | HTML MFA confirmation selected the login template, hiding the one-time recovery-code display. | Medium, recovery availability | Confirmation retains the MFA result view, revokes the enrollment session, and shows recovery codes once. The independent MFA API probe returned eight codes, revoked the old session, accepted one code for login and rejected its reuse. |
| R6 | Non-ASCII strings could reach constant-time string comparisons or malformed token hashing and produce server errors instead of clean rejection. | Medium, robustness | CSRF is constrained to hexadecimal; public tokens have a URL-safe alphabet and fixed length; OTP inputs are constrained/checked before comparison. A non-ASCII CSRF HTTP probe now returns 403. |
| R7 | TOTP enrollment accepted a neighboring time interval but recorded the current interval, allowing reuse of an accepted future code at login. | Medium | Enrollment records the actual matching counter. An independent future-interval enrollment-code replay probe now returns 401. |
| R8 | Invalid administrator CLI input could surface a Pydantic exception containing entered password values. | Medium | Credential schemas hide input in validation errors and the CLI emits a safe failure without a raw exception. A mocked interactive invalid-password probe confirmed the supplied secret is absent from the error. |
| R9 | Production could use an HTTP public origin; plain Settings representations/child configuration could expose SMTP credentials unnecessarily. | Medium, configuration | Production now requires HTTPS, SMTP credentials use SecretStr, validation errors hide inputs, and the scientific child removes SMTP environment variables and skips .env loading. Code review confirmed the guards; no real SMTP delivery was attempted. |

## Executed isolation probes

The reviewer used a temporary SQLite database, the memory email backend and two
synthetic accounts. Both accounts traversed the actual HTTP registration,
verification-email capture, verification POST, login and server-session endpoints.
There was no production authentication bypass or public test-verification endpoint.
A test-only predictor completed a synthetic job through the real incremental
pipeline and export code; this verifies authorization mechanics, not clinical NER.

Sixteen paths were checked for its owner and a different authenticated account:
job HTML, both viewer aliases, token status, job-ID status, progress, document
listing/text, annotations, document statistics/search, individual TXT/ANN,
BRAT/TSV and aggregate statistics. Every owner request returned 200; every foreign
request returned 404 and omitted the synthetic private-text marker. The other
account's history was empty. Job-ID and old token locators use the same mandatory
owner check. There is no ADMIN exception in that check.

An anonymous sweep over the generated OpenAPI route/method inventory found no
unexpected access: private APIs returned 401, private pages redirected with 303,
and public authentication operations required their CSRF precondition. Separate
source review covered HTML-only pages and exact static-resource exceptions.

A separate real administrator bootstrap/email-verification/login probe confirmed:

- Administrative APIs return 403 before MFA enrollment.
- Enrollment verifies a TOTP and revokes the enrollment session.
- Recovery codes are one-use and an MFA-authenticated session can list accounts.
- Account API responses omit password hashes and MFA secrets.
- A revoked cached administrator principal cannot perform an account mutation.

Additional probes re-executed bootstrap collision, invalid-reset hashing,
revoked-session rotation, non-ASCII CSRF, enrollment-code replay and safe CLI error
handling after correction. Only booleans/statuses/counts were printed; no passwords,
session cookies, email action tokens, MFA seeds or recovery codes were retained in
this document or screenshots.

## Access-control paths reviewed

- The ASGI gate is default-deny and runs before upload spooling. Public exceptions
  are narrowly enumerated auth flows, their necessary CSS/JS and minimal health.
- API authentication failures are 401, rather than successful login HTML. Docs and
  OpenAPI are protected; API aliases do not bypass the gate.
- JobService.available enforces ownership before expiry/content handling. The
  document repository, progress, viewer aliases and downloads share that guard.
- History is filtered by owner in SQL. Queue position counts only the caller's
  jobs, avoiding disclosure of other users' queue counts.
- Administrators manage accounts and aggregate operational metrics. Admin routes
  require the actual server-side ADMIN role and an MFA-verified session. Writes
  revalidate the actor inside the same transaction as the mutation/audit event.
- Public account/profile schemas forbid role, tier and owner mass assignment.
  Professional activity is profile information, not an authorization role.
- Old ownerless jobs are not associated by email and remain inaccessible. Additive
  migration does not extend their recorded retention or reset FIFO sequence.
- Passwords use maintained Argon2id with unique salts. Session/action identifiers
  are random and persisted as hashes; MFA/outbox secrets are encrypted with
  purpose-separated keys. Template escaping/textContent and restrictive CSP
  preserve the existing document-XSS boundary.

The complete final method/route/policy/test matrix and full regression/browser,
static-analysis and dependency-audit results belong in SECURITY_AUDIT_V4.md and
VERIFICATION.md. Those broader runs are performed by the implementation agent;
this review does not substitute for them.

## Residual limits

No unresolved high-severity access-control or session flaw was identified in the
reviewed paths after the corrections above. This statement is bounded by the
review scope and probes; it does not establish invulnerability.

Previously delivered documents, downloads, screenshots or clipboard content cannot
be revoked by a server logout. Open-page session guards are a best-effort privacy
measure; the backend must remain authoritative for every new request. Production
requires correctly configured HTTPS/trusted proxies, real SMTP delivery tests,
backup/key protection, institutional legal notices, administrator MFA recovery
procedures and operational rate/resource limits. TOTP remains phishable; it is not
a hardware-bound factor. SQLite/WAL, session throttling and the supervisor remain
single-host controls. Clinical checkpoint/GPU behavior and external-user load were
not assessed in this independent authentication review.

## Maintainer integration follow-up

After the independent probes above, the implementation added host-prefixed cookies
with Path=/ for prefixed installations too; central job-prefix owner enforcement;
opaque-origin form handling corroborated by CSRF/Fetch Metadata; non-renewing idle
polling; and identity-aware cross-tab page clearing. Actual Chromium root/prefix
flows exercise these additions. The reviewer discussed the opaque-origin policy
before its final test run; this follow-up is the maintainer's account, not a claim
of another independent penetration test. SMTP password is the Settings SecretStr;
other SMTP configuration is not described as an encrypted secret in memory.
