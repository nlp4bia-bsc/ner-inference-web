# HTTP API

There are no accounts or session cookies. Successful submissions return a bearer
capability URL. Every private endpoint validates the SHA-256 digest of a 256-bit
random token. No list-jobs endpoint exists. Public responses never expose model
paths, email/name, raw inputs or internal exception messages.

| Method/path | Response |
|---|---|
| GET / | English responsive form |
| GET /jobs/{token} | Private status HTML; its JS polls every 5 seconds while pending |
| GET /api/languages | Array of code/display_name from YAML |
| GET /api/models?language=es | Array of entity/display_name/description/language/model_id/version/available |
| POST /api/jobs | Multipart submission, 202 with job_id/status/token/url |
| GET /api/jobs/{token} | Status, real document counts, queue position, UTC timestamps, summary/download availability |
| GET /api/jobs/{token}/download/brat | ZIP archive attachment when completed |
| GET /api/jobs/{token}/download/tsv | Consolidated TSV attachment when completed |
| GET /api/jobs/{token}/statistics | Strict JSON statistics when completed |
| GET /health | Liveness, 200 |
| GET /ready | SQLite access + fresh worker heartbeat; 200 or 503, includes models_available |
| GET /docs, /openapi.json | Offline API reference and machine-readable OpenAPI schema |

Multipart fields: submitter_name (1–120 characters, trimmed, no controls),
submitter_email (validated EmailStr, normalized lowercase; not verified), language
(two-letter code from catalog), entities (one or more repeated fields), files
(one or more repeated file fields). Choose either TXT files or exactly one ZIP.
Neither public model paths nor inference parameters are accepted.

```sh
curl -X POST http://localhost:8000/api/jobs \
  -F submitter_name=Researcher -F submitter_email=user@example.org \
  -F language=es -F entities=DISEASE -F 'files=@corpus.zip'
```

Example accepted response (token abbreviated for illustration):

```json
{"job_id":"opaque-uuid","status":"QUEUED","token":"random-capability-token","url":"https://temu.bsc.es/jobs/random-capability-token"}
```

Keep the URL: plaintext tokens are returned once and not stored in SQLite. Status
contains job_id, status, document_count, processed_documents (0 until a full batch
completes), queue_position (pending jobs up to this job, excludes active job),
language, entities, created_at, started_at, completed_at, expires_at, error_summary,
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
New document content routes require a valid unexpired capability and an annotated
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
the capability and exact expiry before reading data.

COMPLETED_WITH_ERRORS is a new terminal status. Full-export endpoints offer only
the validated subset with *_partial attachment names and an explicit partial
manifest. FAILED does not offer final batch downloads, though valid previously
published individual documents remain available until expiry. Native final
statistics exclude failed documents and report their operational count separately.
