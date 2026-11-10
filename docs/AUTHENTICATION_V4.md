# Accounts, sessions and data ownership (V4–0.11)

Current administrator approval, cross-owner access, erasure and quota policy:
[Administration 0.11](ADMINISTRATION.md). Historical V4 audit reports describe the
policy at that release; the route inventory describes the current implementation.

This release replaces anonymous capability access. Every work page, catalog,
job/document/progress/export API, API reference and OpenAPI requires a live server
session. Anonymous HTML requests redirect to login; APIs return401. Only exact
login/registration/verification/recovery paths, their exact shared auth CSS/JS, translation vocabulary and supplied logo,
and minimal health endpoints are public. There is no authentication-disable flag.

## Architecture and account model

`app/auth` handles credentials, sessions, CSRF, tokens, encrypted email outbox and
MFA. `app/users/schemas.py` validates allowlisted profile inputs. `permissions`
keeps profession, system role, access tier and ownership distinct. `admin` manages
access requests, accounts, all projects and aggregate operational metrics. Scientific inference does not resolve
users or sessions; ownership/quota checks happen before durable admission.

- Professional activity: CLINICIAN, RESEARCHER, DATA_SCIENTIST, NLP_ENGINEER,
  STUDENT, OTHER. Other requires a short description. These grant no privileges.
- System role: USER or ADMIN. Registration always creates USER; the first
  registrant receives no special treatment. New requests are PENDING until an
  administrator explicitly approves them; pending/rejected users cannot sign in.
- Access tier: STANDARD=100 documents, EXTENDED=1000, UNLIMITED=no administrative
  count limit. An approved administrator can change tiers and assign a
  numeric document_limit override, including zero. Clearing it restores the tier.
  Email verification is required only when explicitly enabled.
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
and progressive rehash. Passwords accept 4–1024 Unicode characters for new
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

As of0.5.4, the default is `REQUIRE_EMAIL_VERIFICATION=false`. New registrations
require a syntactically valid, unique normalized email, but do not send email or
create verification tokens. Duplicate emails return409, including concurrent
registration attempts protected by the database unique constraint. Since0.11, new registrations also require administrator approval. Existing
ACTIVE accounts are migrated to APPROVED. Approved accounts can sign in and submit
within their current custom quota without email verification under the default policy.
`email_verified_at` remains unset unless an actual verification occurred; the UI
shows "Registered email" rather than claiming ownership was verified.

No SMTP is needed for registration or trusted local administrator bootstrap.
Administrator role and MFA requirements, ownership, CSRF and revocation remain
mandatory. Existing hashing/session behavior is unchanged. New passwords have a
four-character minimum in registration/change/reset, including Unicode code-point
validation in the browser; existing-password login is not restricted by the new
password minimum. Confirmation must still match exactly.

`SUPPORT_EMAIL=fernando.gallego@bsc.es` supplies the account/error-report contact
link. It opens the user's mail client. It does not send automatic server error
emails without an SMTP transport. If no mail transport is configured, the login
page offers administrator password help rather than a nonfunctional recovery link.
Email-based password reset remains available when a mail backend is configured.

The previous verification workflow remains available only with the explicit
`REQUIRE_EMAIL_VERIFICATION=true` opt-in. Its instructions follow below.

For the optional verification/recovery email service in production, use
APP_ENV=production, HTTPS PUBLIC_BASE_URL, COOKIE_SECURE=true, MAIL_BACKEND=smtp
and STARTTLS with valid server certificates:

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://temu.bsc.es/ner
APP_PREFIX=/ner
COOKIE_SECURE=true
MAIL_BACKEND=smtp
REQUIRE_EMAIL_VERIFICATION=true
SUPPORT_EMAIL=fernando.gallego@bsc.es
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

For optional local mail testing, explicitly select development/loopback HTTP and
MAIL_BACKEND=file; `.env.example` defaults to MAIL_BACKEND=none. Messages appear as private600 JSON files under
STORAGE_ROOT/test-mail; read the link locally and confirm it in the browser. Tests
also support a memory mailbox. Both capture backends are rejected in production;
there is no HTTP mailbox or public testing verification endpoint.

## MFA disabled by default (0.11.1)

`ENABLE_MFA=false` disables second-factor checks, OTP inputs, setup links and
HTML/API enrollment endpoints (404). Administrators use email/password immediately;
previously enrolled accounts also sign in without a code. Stored MFA records are
preserved, and password-only sessions never claim MFA verification. Existing
approval/role/CSRF/revocation and transactional actor checks remain required.
Only future explicit `ENABLE_MFA=true` restores the TOTP/recovery-code flow
below. No MFA setup or new environment export is required with defaults.

## First administrator and routine administration

Start the web/worker and, only if no administrator exists, create the first
administrator from an interactive terminal. Mail is optional under default policy:

```sh
python -m scripts.create_admin
# Docker, with configured web environment and a terminal:
docker compose exec web python -m scripts.create_admin
```

The command prompts for profile fields and getpass password/confirmation. It
requires a new email and no existing administrator, creates/promotes the new
identity atomically and records ADMIN_BOOTSTRAP. No default password, first-user
rule, password argument or public bootstrap API exists. With the optional email
verification policy enabled, verify the emailed link. Sign in and open `/admin`.
The following enrollment instructions apply only with `ENABLE_MFA=true`: open `/mfa`, re-enter the password, add the displayed secret to an
RFC6238 authenticator and confirm its code. Save the eight recovery codes when
shown once; their HMAC verifiers, not raw values, are stored. Enrollment revokes
its session; sign in again with the next unused TOTP or a recovery code.

`/admin`, `/admin/projects` and `/api/admin/*` require an active, approved ADMIN
and a live session (plus MFA/email verification only if explicitly enabled).
The same gate authorizes foreign project content, exports and management. Search,
approval/decline, role/tier/state/quota changes, session revocation and account/project
erasure are audited. The last active approved administrator is protected; self-account
deletion is rejected. Granting ADMIN requires enrollment only when ENABLE_MFA=true. The
existing administrator is preserved by migration 6. See [Administration](ADMINISTRATION.md).

## Ownership, quotas and history

New jobs derive owner_user_id only from the live session. Job IDs and legacy
43-character tokens are locators, never authorization. Central middleware and
JobService enforce owner access or the explicit administrator gate. Ordinary users
receive 404 for foreign/unowned IDs before file reads; authorized access receives
410 at expiry. Personal history remains owner-filtered, queue positions refer to
the project's owner, and All projects is an explicit administrator view.

Admission counts actual files/ZIP entries/paste documents, checks the per-batch
cap and retained total across jobs, then revalidates live approval/session state
and the fresh custom quota in its SQL write transaction. A large batch is rejected
in full, not truncated. Lowering a quota below occupancy does not delete existing
files. User/system deletion and expiry release retained capacity; upload history
is independent. UNLIMITED removes the administrative count cap, while all byte,
expansion, queue, disk, memory and execution bounds remain. MAX_DOCUMENTS_PER_JOB
is an optional technical ceiling, not the user's retained quota.

Accounts persist until administrator deletion; job files expire72h after terminal
completion. Ownerless legacy jobs keep their original deadlines and cannot be
claimed by email; administrators may inspect them while valid or erase them.
No public ownership-transfer API exists.

## V5 presentation additions

The institutional redesign preserves these gates. Public resources are restricted
to auth.css, auth.js, i18n.js and assets/bsc-blue.svg; private catalog/viewer scripts
and all work routes remain closed. /models and /my-jobs require authentication.
/sessions and /api/auth/sessions return only the current owner's non-secret session
metadata. /account-deletion is a CSRF-protected, throttled and transactionally
revalidated audited request for institutional review, not immediate deletion.
ADMIN can review that event and explicitly delete the account through the 0.11
workflow. Migration6 adds approval and custom quota fields without altering
existing credentials, MFA, sessions or72h deadlines.
See USER_EXPERIENCE.md and REDESIGN_VERIFICATION.md for current UI evidence.
