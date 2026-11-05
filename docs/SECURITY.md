# Security and privacy — V4

All work routes now require live server sessions and strict job ownership. A token
alone grants no access. Default-deny middleware covers old aliases, catalog,
documents/progress/downloads, HTML, API docs and OpenAPI. APIs deny anonymous users
with401; HTML redirects to login. Foreign and historical unowned jobs return404,
including for administrators. Every object access is also guarded in JobService;
no storage directory is mounted publicly. See AUTHENTICATION_V4.md and the complete
method/route/authorization matrix in ROUTE_SECURITY_V4.md.

Users register with normalized email, profile, legal acknowledgment and Argon2id
passwords. Profession grants no privileges. System roles are USER/ADMIN; access
tiers are STANDARD100/EXTENDED1000/UNLIMITED. Public/profile schemas forbid role,
tier and owner mass assignment. Verified email is mandatory for processing and
administration. Administrators must enroll TOTP and use a verified-MFA session;
password-protected enrollment generates protected one-use recovery codes. No first
registrant, default password or public bootstrap/testing bypass creates an admin.

Sessions/action identifiers use256 random bits and hashed verifiers. Production
cookies are HttpOnly/Secure/SameSite=Lax, host-prefixed with Path=/, and carry no
role payload. State-changing operations require CSRF and trusted-origin checks.
Login rotates identity; logout/revocation, idle/absolute expiry, suspension and
password changes are enforced in the database. Sensitive writes revalidate the
session atomically, even after delayed bodies. Automatic polling does not renew
idle activity. API/HTML output never exposes hashes, MFA secrets or session values.
No credentials, clinical text or tokens enter browser persistent storage.

Email verification/recovery are single-use, revocable and expiring. GET links do
not consume tokens. An encrypted durable SMTP outbox retries delivery with TLS;
missing production mail fails503 and never auto-verifies users. Local/file/memory
capture mail is development/test-only, with no public inbox endpoint. Credentials
are not accepted as administrative CLI arguments, echoed in validation errors,
written into logs, or passed to scientific children. Keep the private rate-key
and encrypted volume/backup access under institutional control.

All inputs remain untrusted. TXT/ZIP/paste validation preserves original bytes,
checks UTF-8, file type/count, expansion, compression ratio, duplicate/conflicting
paths, traversal, control characters, encrypted/special/link entries and bounded
body size. ZIP content is not extractall'ed. Per-account limits are derived from
the session and checked on the actual whole batch, atomically with persistent
admission. UNLIMITED retains technical resource limits. Keep external proxy,
connection, filesystem and CPU/memory/GPU budgets; application quotas are not an
OS disk quota or a distributed abuse-control system.

Model files/catalog/receipts are trusted administrative deployment inputs. No
public model/path/URL upload or arbitrary download is available. The supervisor
remains lifetime-exclusive, runs one bounded job child at a time and cleans up
interrupted attempts. Native scientific encoding, offsets, statistics and exports
remain ner_lab. The HTTP dependency audit is clean at the recorded run, but the
upstream neural extra pins torch2.10.0, with two recorded advisories. Do not claim
a fully hardened neural production profile until upstream resolves them; see
SECURITY_AUDIT_V4.md for identifiers, scope, mitigations and audit artifacts.

Responses use no-store/no-referrer/noindex/nosniff/CSP with no third-party auth
assets. Uploaded text is rendered using textContent, never executable HTML.
Templates autoescape profile/catalog values. BRAT/TSV/JSON preserve canonical
scientific text/offsets: spreadsheet consumers must import untrusted surfaces as
text to avoid formula interpretation. No frontend filter alters saved artifacts.

Private files and partial publications still expire72h after terminal completion.
Owner checks happen before expiry/existence metadata is disclosed. Cleanup runs
without browser visits and removes originals, publications, exports, intermediates
and caches, then scrubs job metadata. Persistent account data/audit has a separate
policy. Deletion/unlink is not forensic SSD/backup erasure; encrypt storage and
apply institutional retention to backups. Existing deadlines are not prolonged.

Production still requires the institution's legal notices/data policy, trusted
TLS/HSTS/proxy configuration, real mail-provider validation, key/MFA recovery,
monitoring and capacity validation. Administrators manage accounts/operational
metrics, not clinical access across owners. Local synthetic tests and independent
code review are evidence within their scope, not certification or invulnerability.

## Institutional interface (V5)

The redesign adds no public work page. Only the shared auth vocabulary and the
provided static logo join the exact public asset allowlist. Sessions metadata is
owner-filtered and excludes IDs/verifiers/seeds/IPs; deletion requests reject extra
fields, enforce CSRF/throttling and revalidate the actor transactionally. They are
audited for institutional review. Owner-only dashboard projections do not expose
other accounts' queue counts or source documents. Administration confirmations
are additional UX: the existing live ADMIN/MFA/CSRF checks remain authoritative.
Native dialogs, local SVG/fonts and ES modules preserve the strict CSP.
See REDESIGN_VERIFICATION.md for repeated authorization/browser checks.
