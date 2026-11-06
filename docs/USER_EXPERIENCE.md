# Research workflows

The public entry is Sign in, not a public document-processing landing page. Its
institutional presentation explains interactive annotations, explicit model
selection and BRAT/TSV. On phones, the form comes first and secondary presentation
is reduced. Registration, verification, forgotten/reset password and session-expiry
states use the same shell and footer. No sensitive sample corpus is public.

## Registration and access

Register a name, normalized email, institution, professional activity and password;
confirm the password and acknowledge the notices. Other reveals a required short
description. Password visibility is explicit and reversible. New accounts start as
USER/STANDARD, with 100 documents per job. Neither registration nor profile contains
an editable administrative role or quota. Verification/recovery uses the existing
single-use email links and actual server sessions. Local captured mail remains a
development/test facility; production requires SMTP and HTTPS.

EN/ES/CA is available before login and throughout the authenticated workspace.
Switching interface language happens in place, without clearing an upload, pasted
text, selected checkpoints or a result filter. It does not change document language
or scientific results. Profile has a separate saved preferred-language field.

## Research Workspace and My jobs

The private dashboard welcomes the account holder, shows actual active/completed/
result-available job counts and the backend-derived document cap. Metrics aggregate
only that owner's retained records, independently of paginated history. They are
not all-time institutional statistics. Results available counts jobs with at least
one published document and a valid deadline, including partial jobs.

Recent jobs show source filename as an identifier, language, selected model IDs,
document count, state, progress, timestamps and authorized actions. The dedicated
My jobs route uses the same owner-filtered paginated history. Mobile rows become
cards. Empty accounts get a genuine empty state and a New annotation action; no
placeholder jobs or fabricated activity is inserted.

STANDARD permits 100 documents, EXTENDED 1000; UNLIMITED removes the administrative
count cap while technical controls still apply. A configured technical ceiling can
further reduce the effective cap shown by the backend. Ordinary users cannot edit
these values. Changes apply to new admissions.

## New annotation and Models

New annotation has four sections: Input documents, Language, Entities and models,
Review and submit. Paste text, multiple TXT and a ZIP with TXT folders keep their
existing ingestion paths. Drag/drop and conventional file selection coexist;
selected names/counts/sizes and removal controls reflect actual browser File objects.
Pasted text shows Unicode character/UTF-8 byte counts. There is no fabricated upload
progress: XHR reports transferred bytes, followed by server validation/admission.
ZIP document counts are validated on the server, never guessed from archive size.

Checkpoint categories are peers, with an explicit collapsible multilingual section. Collapsing it keeps existing
selections, and opening it never selects a checkpoint. Opening a
category selects nothing. Availability, source repository, version, languages and
registered metrics are inspectable. Unavailable models are disabled. Multilingual
bindings must be validated for the chosen document language. The read-only Models
page reuses this catalog, requires login and makes no clinical performance claim.

Acceptance acknowledges the durable queue and links to the owned job. Possession
of that link is never authorization. A completion dialog appears only after an
observed actual state transition and offers permitted viewer/BRAT/TSV actions; it
is not repeatedly triggered on every poll or for a previously completed job.

## Document exploration

The wide viewer retains folder trees, filename/path search, annotation/state
filters, sorting, pagination, document navigation and individual TXT/ANN downloads.
Text search preserves original Unicode offsets. Category and model filters affect
only the displayed mentions. Keyboard activation of a highlighted region exposes
all covering annotations; list/table selection stays synchronized with the text.
Alt+Left/Right navigates mentions outside input fields. Mobile details use a native
modal sheet, and every legitimate annotation remains available.

Details show surface text, offsets, category, original sublabels, supporting model
IDs/versions and individual prediction scores when provided. Neither offsets nor
consolidation algorithms changed for this redesign. Missing statistics/scores stay
unavailable rather than being replaced by invented numbers.

Progress uses backend document states, supports compact/expanded presentation and
continues while partial results are browsed. Completed work opens compactly.
Deletion countdown uses actual server time and expires independently of locale or
refresh. Expired results clear, downloads are removed and backend expiry checks
remain authoritative. Session revocation/change of account also clears the old
view and shows a translated sign-in notice; copied/downloaded data cannot be recalled.

The annotation reader also offers **Inline highlights** and **Entity towers**.
Inline overlaps use a double underline without counters inside words. Towers
show one centered category/ID tag per entity in independent blocks per source line.
Shorter overlaps appear nearest the text, with longer mentions above them,
including multiword and wrapped mentions. Selecting a tag opens its full surface,
original `[start, end)` range and provenance. The end is exclusive. Canonical
colors remain the same across languages; changing the reading mode changes only
presentation. Both views preserve the original text and scientific records.
Tower marks are invisible initially. Clicking a label or pressing Enter/Space
shows only its range marks; activating it again hides them. Labels remain in place.
Original model-label aliases share category colors and new labels get stable
extension colors instead of appearing uniformly gray.

## Registration policy since0.5.4

Create account accepts a matching password of4–1024 Unicode characters and checks
email uniqueness. Success opens Sign in with a confirmation; there is no email
verification step. A duplicate address shows an explicit error and leaves the
existing account unchanged. SMTP is not required. The profile says Registered
email without falsely marking the email as verified. The account starts at the
existing STANDARD tier. Administrator actions still require ADMIN plus MFA.

Account/help links open a message to fernando.gallego@bsc.es in the user's mail
client. Automatic server email requires a configured mail transport. Without one,
password help points to the administrator. Older verification descriptions in
this document apply only to the explicit legacy opt-in policy.

## Profile, sessions and administration

Profile displays identity, verification, institution/profession, saved language,
tier and effective limit. Only allowlisted profile fields can be edited. Security
links lead to password change, MFA, active sessions and logout-all. Session listing
returns only creation, last activity, expiry and a current-session flag; no raw
identifier/hash, IP, CSRF seed or other user's session is returned.

Account deletion request records ACCOUNT_DELETION_REQUESTED for institutional
review after a CSRF-protected, throttled and transactionally revalidated write. It
is not immediate deletion. Administrators can see the request in audit history;
actual identity verification, handling and legal/account retention decisions need
an institutional procedure. It does not change job TTL or silently send email.

Administration is visible only to ADMIN and still requires verified email and an
MFA-verified session on the server. Search, account/tier/state/role changes, session
revocation, aggregate metrics and audit history use the existing authorization.
Sensitive actions require a visual confirmation; cancelling leaves the account
unchanged. Administrators gain no access to other owners' clinical documents.

## Institutional notices and remaining operations

The reusable footer includes the unchanged supplied BSC SVG, NLP4BIA identity,
repository/documentation, draft privacy/terms for institutional review and version.
No contact address, legal approval, publication or certification was invented.
[PRIVACY_NOTICE.md](PRIVACY_NOTICE.md) and [TERMS_OF_USE.md](TERMS_OF_USE.md) are
explicit drafts, not final institutional legal notices.

Deployment remains the same FastAPI/SQLite single-host application. Configure
HTTPS/proxy trust, SMTP, private storage/keys and validated checkpoints as documented
in [DEPLOYMENT.md](DEPLOYMENT.md). The redesign does not resolve the disclosed
upstream Torch advisories or validate clinical/GPU performance.
