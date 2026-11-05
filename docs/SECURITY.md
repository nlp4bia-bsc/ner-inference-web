# Security and privacy

Public input is untrusted; checkpoint directories/YAML/receipts are trusted
administrator inputs. There is no registration, verified personal identity or
email notification. Name/email identify request metadata only, never NLP entities.
Deploy only with the data policy applicable to the institution and corpus.

Capability tokens use secrets.token_urlsafe(32); SQLite stores only SHA-256 hashes.
Invalid tokens receive the same 404 as unknown ones. Possessing a valid link grants
access to texts, annotations and submitter metadata inside the downloads. Do not
share these links. Status API intentionally omits submitter PII. HTTPS is required
in production, with no-store/no-referrer/noindex/nosniff/CSP headers. No third-party
assets load on form/status pages. Disable request URL logging in Uvicorn, proxy and
APM. Application logs record job ID and exception type only; full exceptions can
contain clinical text and are deliberately not emitted.

Rate keys are HMAC-SHA256 of IP/email using a private persistent local key. Separate
IP/email checks and updates are atomic with job admission in SQLite, so changing
only email cannot bypass IP limits. Emails are normalized lowercase, not verified;
this is an abuse control, not proof of identity. Proxy forwarding is disabled by
default and can only be enabled for a strictly configured trusted proxy chain.
No cookies/session authentication exist. Same-origin browser form submissions are
checked against PUBLIC_BASE_URL when Origin is supplied; origin-free API clients
remain supported. No permissive CORS policy is installed.

TXT/ZIP ingestion checks actual byte sizes, per-document/aggregate limits, count,
entry count, compression ratio, path traversal/absolute/drive/backslash/control
paths, encrypted/special/link entries, duplicates (casefold), binary controls,
UTF-8 decoding and conflicting directory/file paths. Nested ZIPs and non-TXT entries
are rejected, not ignored. Empty text is rejected to match ner_lab's corpus
contract. ZIP contents are never extractall'ed; bounded bytes are written into a
new private staging directory after validation. ZIP metadata, archives and original
names are never trusted as unrestricted filesystem paths. Original TXT bytes are
preserved; no silent newline/unicode normalization affects offsets.

Request admission is bounded before multipart parsing, even without Content-Length.
Persistent upload leases, hard body timeout and conservative storage reservations
protect disk/memory. Use proxy connection/rate bounds, container resource limits,
a dedicated filesystem quota and restricted egress for stronger protection against
resource exhaustion. The inference supervisor has a hard job timeout, child death
handling and a lifetime lock. Only trusted local checkpoints may execute; no
public model/path/URL injection and no arbitrary runtime model downloads.

Private storage is never statically served. Every download checks token, terminal
state and expiry; hiding UI controls is not an access control. Cleanup runs without
browser visits, removes input/output/temp files, scrubs live PII and removes
minimal tombstones after the configured period. Expired downloads return 410 even
before the next sweep. Retention cannot run while the host is stopped. Filesystem
unlink and SQLite deletion are not forensic erasure; backups, WAL/media encryption
and institutional data-retention procedures remain deployment responsibilities.

BRAT/TSV/JSON export preserves offsets and original text. TSV uses ordinary quoted
fields for interoperability; spreadsheet users must import columns as text because
untrusted surfaces/names may begin with formula characters. Escaping them in the
canonical file would change scientific data. No HTML rendering of uploaded text
occurs; JS uses textContent and templates autoescape values.

Known limits: single host/local disk, no distributed rate limits across separate
storage roots, no authentication beyond bearer capabilities, no antivirus scanner,
no user cancellation, no model sandbox beyond OS/container controls, no gold-based
evaluation and no anonymization of clinical corpora. Models should be supplied
only by trusted administrators. Production readiness requires real checkpoint and
BSC infrastructure validation; these are not implied by mock/synthetic tests.
