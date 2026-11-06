# HTTP API

Every work/catalog/document/progress/download route requires a live server
session. Private APIs/OpenAPI return401 without it; HTML redirects303 to login.
Job IDs and legacy tokens are locators only: every route requires strict ownership
(without an ADMIN bypass) and an unexpired job. Unknown/foreign/unowned resources
return404. Name/email come from the account, never from a claimed owner field.
Public exceptions and the complete method/policy matrix are in ROUTE_SECURITY_V4.md.

Auth APIs accept JSON (public actions also require csrf_token from the login/register
page and its challenge cookie). After login, GET /api/auth/session returns the
public profile and csrf_token; send X-CSRF-Token with authenticated writes. Cookies
are HttpOnly/Secure in production and must not be copied into browser storage.

| API | Purpose |
|---|---|
| POST /api/auth/register | name/email/institution/profession/Other/password/confirmation/legal acceptance; USER+STANDARD only |
| POST /api/auth/login | email/password and optional TOTP/recovery code; fresh session cookie |
| POST /api/auth/verify-email, /resend-verification | one-use token confirmation / generic email request |
| POST /api/auth/forgot-password, /reset-password | generic email request / token+new password+confirmation |
| GET /api/auth/session | own public profile and CSRF proof |
| POST /api/auth/logout, /logout-all, /rotate-session, /touch | revoke / all-revoke / bounded rotation / actual interaction |
| POST /api/auth/change-password | current password and new password+confirmation; revoke all sessions |
| GET/PATCH /api/profile | own allowlisted profile; roles/tiers/email/owner cannot be edited |
| GET /api/my/jobs?offset=0 | paged owner-only history, maximum100 rows |
| POST /api/auth/mfa/start, /mfa/confirm | password-protected TOTP enrollment, one-time recovery-code display |
| GET /api/admin/users, /metrics, /audit | verified ADMIN+MFA account management/aggregate audit, no clinical access |
| PATCH /api/admin/users/{identity} | allowlisted role/tier/state change, atomically audited |
| POST /api/admin/users/{identity}/revoke-sessions | audited real revocation |

Field contracts and defaults are in AUTHENTICATION_V4.md. Malformed fields never
echo passwords or tokens; extra privilege/profile fields are rejected. Public
capture/testing inboxes and public bootstrap/verification bypasses do not exist.


| Method/path | Response |
|---|---|
| GET / | Private personal dashboard; /annotate serves the NER form |
| GET /jobs/{token} | Private status HTML; its JS polls every 5 seconds while pending |
| GET /api/languages | Authenticated array of code/display_name from YAML |
| GET /api/models?language=es | Category/checkpoint rows, neutral model_name, supported languages, availability/reason, label mapping, dependencies and verified metrics |
| POST /api/jobs | Multipart submission, 202 with job_id/status/token/url |
| GET /api/jobs/{token} | Status, real document counts, queue position, UTC timestamps, summary/download availability |
| GET /api/jobs/{token}/download/brat | ZIP archive attachment when completed |
| GET /api/jobs/{token}/download/tsv | Consolidated TSV attachment when completed |
| GET /api/jobs/{token}/statistics | Strict JSON statistics when completed |
| GET /health | Liveness, 200 |
| GET /ready | SQLite access + fresh worker heartbeat; 200 or 503, minimal status only |
| GET /docs, /openapi.json | Offline API reference and machine-readable OpenAPI schema |

Multipart fields: submitter_name (1–120 characters, trimmed, no controls),
submitter_email (validated EmailStr, normalized lowercase; not verified), language
(two-letter code from catalog), models (one or more repeated checkpoint IDs), files
(one or more repeated file fields). Choose either TXT files or exactly one ZIP.
Submitter name/email are optional legacy inputs; the server uses account identity.
The server derives the canonical category set. Optional repeated entities must
match that set. Legacy entities-only requests retain their original single-model
selection; new ambiguous categories require explicit models. No model is selected
implicitly by the frontend. Neither public model paths nor inference parameters
are accepted.

```sh
curl -X POST http://127.0.0.1:8000/api/jobs \
  --cookie /private/session-cookies --header 'X-CSRF-Token: <session-csrf-proof>' \
  -F language=es -F models=bsc-bio-ehr-es-distemist -F models=bsc-bio-ehr-es-carmen-distemist -F 'files=@corpus.zip'
```

Example accepted response (token abbreviated for illustration):

```json
{"job_id":"opaque-uuid","status":"QUEUED","token":"random-capability-token","url":"https://temu.bsc.es/jobs/random-capability-token"}
```

In local development, `localhost` and `127.0.0.1` are accepted on the configured
scheme/port. The accepted URL preserves the validated browser host so it does not
cross into the other hostname's cookie jar. Production still uses its configured
origin; untrusted Host/forwarding values cannot supply a private-link origin.

Keep the locator URL: token hashes are stored for compatibility, but tokens
never authorize anonymous or cross-account reads. Status
contains job_id, status, document_count, processed_documents (0 until a full batch
completes), queue_position (pending jobs up to this job, excludes active job),
language, entities, models (resolved checkpoint IDs), created_at, started_at, completed_at, expires_at, error_summary,
summary and downloads_available. Timestamps are ISO-8601 UTC; the browser formats
them in the visitor's local timezone.

Errors use `{ "detail": "safe user-facing message" }`; form validation may add
field names. 422 invalid metadata/catalog/TXT/ZIP; 400 malformed length or
multipart; 403 origin mismatch; 404 invalid/unknown token; 408 upload timeout;
409 results not ready/failed; 410 expired; 413 byte/ratio limits; 429 IP or email
rate limit (Retry-After seconds); 503 queue/upload/storage saturation, missing
artifact or worker not ready. HTTP body limits apply without Content-Length.

GET status returns 410 after terminal expiry and 404 after tombstone removal;
private HTML can still render the expiry message while a tombstone exists.
Download endpoints check the deadline independently of cleanup. No static mapping
points into input/output storage. All responses carry no-store, no-referrer,
noindex, nosniff and a same-origin CSP.

## Phase 2 additions and prefix

All routes can be mounted with APP_PREFIX=/ner; set PUBLIC_BASE_URL with the same
path. Existing unprefixed contracts are unchanged when APP_PREFIX is empty.
New document content routes require a live session, strict owner and unexpired job and an annotated
document; metadata can be read during processing. 404/409/410 apply before reading files. OpenAPI exposes Pydantic document/text/annotation/statistics schemas.

| GET path (append to /api/jobs/{token}) | Parameters / response |
|---|---|
| /viewer | Read-only HTML explorer |
| /documents | offset>=0, limit 1..100 (default 50), q, label, has_annotations; items/total/offset/limit |
| /documents/{document_id} | start>=0, limit 1..50000 (default 10000); text/start/end/total_characters and filename/ID |
| /documents/{document_id}/annotations | offset>=0, limit 1..500 (default 200), start/end overlap range, label/q; canonical records with absolute offsets |
| /documents/{document_id}/search | q (1..200 characters), start>=0; next exact-match start/end, total non-overlapping count, wrapped flag |
| /documents/{document_id}/statistics | document_id and native per-document statistics |

No filename/path is accepted as a filesystem selector. IDs resolve from the
job's private index. Fragment clipping changes the text response only; returned
annotations retain complete original surfaces and document coordinates even when
crossing the fragment boundary. No text from other documents is bundled.

The HTML reference is served locally without Swagger CDN scripts; it lists operations and response/request model fields. No third-party runtime asset is required.

## V3 incremental inputs and progress

POST accepts exactly one input mode: PASTED_TEXT (pasted_text or a UTF-8
pasted_text_file part, optional document_name), TXT_UPLOAD (one/many files), or
ZIP_ENTRY (one ZIP). Omitted input_mode keeps legacy file-only inference. Mixed
text/files and unknown modes are rejected. Browser paste uses a UTF-8 Blob to
avoid multipart textarea line-ending conversion; stored bytes are unchanged.

GET /api/jobs/{token}/progress exposes persisted document counts, stage, percentage,
updated_at, server_now, expires_at, queue_position and provisional native-statistic
sums. Percent means ANNOTATED/total, excludes failures, and is not time progress.
Server time synchronizes the monotonic browser countdown. PREPARING_DOWNLOADS is
an explicit nonterminal stage. Existing GET status adds server_now/progress.

Document listing now includes PENDING/PROCESSING/ANNOTATED/FAILED, source_type,
relative_path and safe error_code, with status filtering and optional sort=name.
Only ANNOTATED documents expose text/annotations/statistics/individual downloads;
409 protects unfinished documents. Lists are available while processing.

GET /jobs/{token}/viewer is an alias for the existing API viewer URL and opens
when at least one annotated document is published. GET
/api/jobs/{token}/documents/{document_id}/download/txt and /download/ann provide
individual validated artifacts, including during processing. Every route checks
the session, strict owner and exact expiry before reading data.

COMPLETED_WITH_ERRORS is a new terminal status. Full-export endpoints offer only
the validated subset with *_partial attachment names and an explicit partial
manifest. FAILED does not offer final batch downloads, though valid previously
published individual documents remain available until expiry. Native final
statistics exclude failed documents and report their operational count separately.

## Canonical categories and supporting predictions

Annotations consolidate only equal document/category/offset tuples. Each item adds
`model_ids`, `original_labels` and `sources` containing every distinct model/version/
original-label/score prediction. Top-level `model_id`, `model_version`, `score`
remain for compatibility and represent the deterministic highest-score source.
Different offsets or categories remain separate selectable overlapping spans.
TSV appends the same provenance as JSON-encoded cells. Old saved viewer indexes and
TSVs without these optional fields remain readable.
