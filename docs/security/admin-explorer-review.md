# Administrator explorer review — 0.12

Reviewed 2026-11-11 during implementation; developer review, not an independent
penetration test or a certification. See [verification](../VERIFICATION.md).

- New explorer endpoints share the existing router's ADMIN dependency. Services
  also revalidate the live approved/active actor, with optional MFA only when
  enabled. Identity/owner values are bound SQL parameters. Profiles expose a
  fixed safe field list. The application prefix is not an authorization mechanism.
- Project statistics acquire the publication/deletion lock and recheck session,
  role and expiry after waiting. A concurrent demotion revokes the in-flight read.
  Global aggregation rechecks the project set and document-set generation;
  concurrent project/document erasure cannot restore a previously read count.
- Counts come from canonical published annotation files, including partial NER and
  normalization phases, not selected model lists or stale terminal summaries.
  The LRU stores bounded numeric aggregates without mention text, terms or codes.
  Missing/corrupt publications are identified as incomplete rather than invented.
- Original/annotation/viewer/download links reuse existing guarded routes. The
  viewer's document query is resolved through those routes; concurrent refreshes
  share its initialization and cannot select the first unrelated document.
- Destructive tree actions reuse existing CSRF/live-role-protected services. The
  dialog identifies the document/project; cancellation leaves data intact. Audit
  records opaque project/document/owner identifiers. Erasure fences late workers
  and releases the real owner's retained quota while preserving upload history.
- Legacy results reuse the existing TSV backfill. Before individual erasure,
  retained originals become canonical publications under the same lock/transaction.
  This preserves surviving overlaps/normalizations and adopts historical ledger
  IDs without increasing lifetime upload counts. No schema/volume recreation.
- Dynamic UI content uses textContent and encoded identifiers, never injected
  source HTML. Native nested details/summary supports keyboard disclosure;
  pagination bounds lists, annotations remain paged and sensitive page state is
  held only in memory. Expiry clears open annotation nodes and counts before the
  asynchronous refresh, using monotonic time relative to server timestamps.
- Compose retains the loopback-only backend binding and existing volume. The exact
  requested Apache profile trusts forwarded headers; production relies on Apache
  setting the HTTPS scheme and the backend port remaining private. No Caddy,
  WordPress, certificate, server .env or deployment volume was changed here.

The aggregate is assembled from consistent per-project reads; it is not an
all-corpus write lock or a historical analytics database. Ordinary inference can
publish between scope reads, and Refresh obtains newer statistics. Already
viewed/downloaded material cannot be recalled. Real server TLS/Apache delivery,
physical CPU instruction support and production backups require deployment-side
checks; local synthetic browser/HTTP tests do not establish those properties.
