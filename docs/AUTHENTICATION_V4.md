# V4 accounts, sessions and data ownership

This release replaces anonymous capability access. Every work page, catalog,
job/document/progress/export API, API reference and OpenAPI requires a live server
session. Anonymous HTML requests redirect to login; APIs return401. Only exact
login/registration/verification/recovery paths, their two essential static assets,
and minimal health endpoints are public. There is no authentication-disable flag.

## Architecture and account model

`app/auth` handles credentials, sessions, CSRF, tokens, encrypted email outbox and
MFA. `app/users/schemas.py` validates allowlisted profile inputs. `permissions`
keeps profession, system role, access tier and ownership distinct. `admin` manages
accounts and aggregate operational metrics. Scientific inference does not resolve
users or sessions; ownership/quota checks happen before durable admission.

- Professional activity: CLINICIAN, RESEARCHER, DATA_SCIENTIST, NLP_ENGINEER,
  STUDENT, OTHER. Other requires a short description. These grant no privileges.
- System role: USER or ADMIN. Registration always creates USER; the first
  registrant receives no special treatment.
- Access tier: STANDARD=100 documents, EXTENDED=1000, UNLIMITED=no administrative
  count limit. Only an MFA-authenticated, verified administrator can change tiers.
- Profile: name, normalized email, institution, professional activity/description,
  preferred locale, legal acknowledgment timestamp, verification/account state,
  role/tier and creation/update timestamps. Password confirmation is transient;
  only one Argon2id hash is persisted. Profile APIs cannot change email/roles/tiers.

All user-facing auth pages default to English, with complete Spanish/Catalan
translations. The language selector also works before login and on verification/
recovery links. Emails use the account's preferred locale. Clinical document
language is separate; changing UI locale never changes permissions or source text.

## Credentials and sessions

Argon2id uses 19MiB, two iterations and parallelism1, with library-generated salts
and progressive rehash. Passwords accept 15–1024 Unicode characters for new
credentials, including spaces; there is no truncation or normalization. Login
supports existing passwords within the transport bound. Confirmation is checked
but never stored. Schemas hide inputs in validation exceptions; APIs never return
password hashes and the interactive CLI does not print entered credentials.
See the [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Opaque sessions use 256 random bits; SQLite stores a SHA-256 verifier, user ID,
absolute/idle timestamps, CSRF seed, authentication generation and MFA state.
Cookies are HttpOnly, Secure and SameSite=Lax in production, with no Domain.
Production uses `__Host-` names and **Path=/** even under `/ner`; a deterministic
prefix-specific name separates installations on the same host. This blocks
subdomain Domain-cookie injection. Cookie Path is not an isolation boundary between
untrusted applications sharing an origin: use a separate trusted host when needed.
Development/test can explicitly use insecure cookies only on loopback/test origins.

Default session lifetime is12h and idle timeout30min. Navigation and authenticated
writes renew idle activity. Automatic API/progress/session polling does not;
private browser pages send a CSRF-protected activity POST at most once per minute
in response to actual pointer/keyboard interaction. Explicit session rotation
revokes the previous token and preserves the original absolute deadline. Login
always creates a fresh token. Logout revokes the server record; logout-all,
password reset/change and account suspension invalidate older sessions.

Sensitive writes revalidate the live session inside their SQLite transaction,
including after a delayed upload. Role/account state comes from the database,
not a signed role cookie. An administrator removed or suspended during an upload
cannot finish the request with a cached principal. Open pages check session state
on focus/pageshow/visibility and periodically even after inference completes;
a401 clears the page and redirects. Already downloaded/copied material cannot
be revoked. Browser storage never contains credentials, tokens or clinical text.

## CSRF, origins and abuse bounds

All writes, including login, registration and recovery, require a valid HMAC CSRF
proof. Public forms use a cryptographic pre-login cookie; authenticated forms and
APIs use the server session's seed. APIs use X-CSRF-Token; browser forms can submit
the hidden csrf_token. Responses do not allow cross-origin API reads. Cross-site
Fetch Metadata and mismatched origins are rejected. Chromium HTML form posts can
send Origin:null under no-referrer; this is accepted only with
Sec-Fetch-Site:same-origin **and** the valid cookie/session/HMAC. Null with absent,
none, same-site or cross-site metadata is rejected. Admission trusts only the
internal gate's completed-CSRF marker, never a request header claiming success.

Auth/account/admin bodies have a64KiB limit and total30s deadline. Job uploads keep
the existing bounded disk spool and300s deadline. Persistent HMAC IP/email counters
throttle login, registration, recovery, password changes and MFA. Blocked IPs do
not create unlimited new email-counter rows. Unknown accounts use an Argon2 dummy
comparison; invalid login and recovery responses do not reveal account existence.
Proxy connection/rate limits and filesystem quotas remain deployment controls.

## Verification and recovery

Verification and password-reset identifiers are random, hashed, purpose-separated,
single-use and revocable. Defaults: verification24h, password reset30min. Email
links open a confirmation page; GET does not consume a token, protecting against
mail-scanner previews. The account is obtained from the token record; email/next/
owner parameters cannot switch accounts. Reset never silently verifies email or
logs the user in. It changes the password and revokes all old sessions/resets.
Change password requires the current password. Old/revoked/expired/malformed tokens
fail without invoking the password hasher. Enrollment TOTP codes and recovery codes
are also one-use; enrollment records the actual accepted time-step counter.

## Email configuration

Production requires APP_ENV=production, HTTPS PUBLIC_BASE_URL, COOKIE_SECURE=true,
MAIL_BACKEND=smtp and STARTTLS with valid server certificates:

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://temu.bsc.es/ner
APP_PREFIX=/ner
COOKIE_SECURE=true
MAIL_BACKEND=smtp
SMTP_HOST=your-authorized-smtp-host
SMTP_PORT=587
SMTP_USERNAME=your-service-identity
SMTP_PASSWORD=
SMTP_FROM=your-authorized-sender@example.org
SMTP_STARTTLS=true
```

Supply the real password through a private deployment secret/environment, not Git,
CLI arguments or logs. Settings masks it; Compose gives SMTP settings only to web.
The scientific child also strips SMTP variables and skips .env loading.

Mail is queued durably with an encrypted payload, claimed transactionally, sent
with TLS and retried up to five times. Delivered payloads are scrubbed. Failures
log only exception type; aggregate failures are visible to administrators. Fix the
transport and use resend verification/recovery to issue a new token. Missing mail
configuration returns503 explicitly, never auto-verifies an account. Unverified
accounts cannot submit any processing job or enter administration.

For local development only, `.env.example` selects development/loopback HTTP and
MAIL_BACKEND=file. Messages appear as private600 JSON files under
STORAGE_ROOT/test-mail; read the link locally and confirm it in the browser. Tests
also support a memory mailbox. Both capture backends are rejected in production;
there is no HTTP mailbox or public testing verification endpoint.

## First administrator and routine administration

Configure mail, start the web/worker and create the first administrator from an
interactive terminal:

```sh
python -m scripts.create_admin
# Docker, with configured web environment and a terminal:
docker compose exec web python -m scripts.create_admin
```

The command prompts for profile fields and getpass password/confirmation. It
requires a new email and no existing administrator, creates/promotes the new
identity atomically and records ADMIN_BOOTSTRAP. No default password, first-user
rule, password argument or public bootstrap API exists. Verify the emailed link,
sign in, open `/mfa`, re-enter the password, add the displayed secret to an
RFC6238 authenticator and confirm its code. Save the eight recovery codes when
shown once; their HMAC verifiers, not raw values, are stored. Enrollment revokes
its session; sign in again with the next unused TOTP or a recovery code.

`/admin` and `/api/admin/*` require the actual ADMIN role, verified email and an
MFA-verified session. They support user search, tier/role/state changes, session
revocation, aggregate metrics and administrative history. Changes are audited
atomically. The last active administrator cannot be removed. Granting ADMIN to
another user still requires that user to verify email/enroll MFA; it never grants
clinical access to other owners' jobs. MFA recovery limits are in RECOVERY_V4.md.

## Ownership, quotas and history

New jobs store owner_user_id exclusively from the live session. Job IDs and legacy
43-character tokens are both locators, never authorization. A central route guard
and JobService enforce strict equality with the owner, without an ADMIN bypass.
Unknown/foreign/unowned jobs return the same404 before any file read; only an
owner can receive expiry410. History is owner-filtered in SQL and paged by100;
queue position counts only that user's pending requests.

Submission counts actual TXT files/ZIP contents/paste documents and validates the
account-derived cap before accepting anything. The complete admission transaction
revalidates the owner's session/state/verification and quota against the actual
count. A too-large batch is rejected in full, not truncated. A request snapshots
its server-derived tier at start; changes apply to subsequent requests. UNLIMITED
keeps all byte, expansion, compression-ratio, ZIP-entry, queue, disk, memory and
execution bounds. MAX_DOCUMENTS_PER_JOB is now an optional **technical** ceiling,
unset by default; it is not the per-user administrative tier. Keeping an old value
of1000 will also cap UNLIMITED at that technical ceiling, so review old .env files.

Accounts are persistent, while job files still expire72h after terminal completion.
Historical jobs with no owner are inaccessible, are not claimed by matching email,
and keep their original deadlines/FIFO. There is no public ownership-transfer API.
