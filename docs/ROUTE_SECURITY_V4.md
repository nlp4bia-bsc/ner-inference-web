# V4 route security inventory

Relative routes; APP_PREFIX is prepended uniformly, including /ner. Anonymous HTML requests redirect303 to login; private APIs/OpenAPI return401. All state-changing requests require CSRF and origin checks. Methods not explicitly routed never bypass the gate.

Public assets: /static/assets/bsc-blue.svg, /static/auth.css, /static/auth.js, /static/i18n.js. No data/storage directory is mounted publicly.

| Method | Route | Authentication | Authorization policy | Ownership | Coverage |
|---|---|---|---|---|---|
| GET | / | Session | Own account and owner-filtered history | SQL owner filter; no foreign queue counts | two-user history + anonymous sweep |
| GET | /account-deletion | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /admin | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| GET | /annotate | Session | Verified email; CSRF for POST; account quota atomically | Owner from session only | quota + unverified + delayed-upload tests |
| GET | /api/admin/audit | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| GET | /api/admin/metrics | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| GET | /api/admin/users | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| GET | /api/auth/session | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /api/auth/sessions | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /api/jobs/{token} | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/documents | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/documents/{document_id} | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/documents/{document_id}/annotations | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/documents/{document_id}/download/{format} | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/documents/{document_id}/search | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/documents/{document_id}/statistics | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/download/brat | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/download/tsv | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/progress | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/statistics | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/jobs/{token}/viewer | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /api/languages | Session | Authenticated shared model metadata | No job data | catalog + anonymous sweep |
| GET | /api/models | Session | Authenticated shared model metadata | No job data | catalog + anonymous sweep |
| GET | /api/my/jobs | Session | Own account and owner-filtered history | SQL owner filter; no foreign queue counts | two-user history + anonymous sweep |
| GET | /api/profile | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /change-password | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /dashboard | Session | Own account and owner-filtered history | SQL owner filter; no foreign queue counts | two-user history + anonymous sweep |
| GET | /docs | Session | Authenticated schema access | No clinical contents | anonymous sweep |
| GET | /forgot-password | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| GET | /health | Public minimal | None | No job data | anonymous sweep |
| GET | /jobs/{token} | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /jobs/{token}/viewer | Session | Central and service owner guard + expiry | Strict owner only; ADMIN has no bypass | two-user API/browser + legacy/TTL |
| GET | /login | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| GET | /mfa | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /models | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /my-jobs | Session | Own account and owner-filtered history | SQL owner filter; no foreign queue counts | two-user history + anonymous sweep |
| GET | /openapi.json | Session | Authenticated schema access | No clinical contents | anonymous sweep |
| GET | /profile | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /ready | Public minimal | None | No job data | anonymous sweep |
| GET | /register | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| GET | /resend-verification | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| GET | /reset-password | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| GET | /sessions | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| GET | /static | Session except exact public auth assets | No storage mount | No job files | anonymous sweep + browser |
| GET | /verify-email | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| HEAD | /openapi.json | Session | Authenticated schema access | No clinical contents | anonymous sweep |
| HEAD | /static | Session except exact public auth assets | No storage mount | No job files | anonymous sweep + browser |
| PATCH | /api/admin/users/{identity} | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| PATCH | /api/auth/profile | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| PATCH | /api/profile | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /account-deletion | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /admin/users/{identity} | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| POST | /api/admin/users/{identity}/revoke-sessions | Session | Live ADMIN + MFA; atomic revalidation for writes | No clinical access | admin/MFA tests + independent review |
| POST | /api/auth/change-password | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/forgot-password | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /api/auth/login | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /api/auth/logout | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/logout-all | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/mfa/confirm | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/mfa/start | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/register | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /api/auth/resend-verification | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /api/auth/reset-password | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /api/auth/rotate-session | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/touch | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /api/auth/verify-email | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /api/jobs | Session | Verified email; CSRF for POST; account quota atomically | Owner from session only | quota + unverified + delayed-upload tests |
| POST | /change-password | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /forgot-password | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /login | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /logout | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /logout-all | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /mfa/confirm | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /mfa/start | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /profile | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /register | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /resend-verification | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /reset-password | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
| POST | /rotate-session | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /touch | Session | Own account/session only; CSRF for writes | Identity from live session; allowlisted fields | auth lifecycle + anonymous sweep |
| POST | /verify-email | Public authentication | CSRF for writes; throttle; validated fields | One-use verifier for account actions | auth_v4 + real browser |
