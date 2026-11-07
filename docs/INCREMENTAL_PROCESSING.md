# Phased inference and recovery (0.10)

Each accepted source has a document reference, original relative path, source
type, byte size and PENDING status. Original UTF-8 bytes remain private files.
Owners can open/read/download their documents immediately after admission,
including while QUEUED, PROCESSING or FAILED. An annotation request returns an
empty list before the first prediction. Login, ownership, deletion and expiry
checks apply to every read; a private link alone grants no access.

## Corpus-wide phases

The lifetime-exclusive supervisor runs one job child at a time. The single
`process_job` orchestration delegates document work to `DocumentPhases`:

1. Readable originals are available as soon as upload/admission finishes.
2. Run the first selected NER model over the whole retained corpus, in bounded
   `INFERENCE_DOCUMENT_BATCH_SIZE` microbatches (default 32). Validate offsets,
   merge that member with prior members and publish each completed batch.
3. Run the next NER member over the corpus, adding its predictions. Preserve
   deterministic deduplication, source provenance, overlapping labels and original
   Unicode code-point offsets. Dependent classifiers receive their saved upstream
   predictions; a failed dependency cannot masquerade as an empty success.
4. Release resident NER models. If normalization was requested, process DISEASE,
   then MEDICATION, PROCEDURE and SYMPTOM when selected. Complete one category over
   all documents before starting the next. Publish every normalization batch;
   disease concepts are readable while medication/symptom processing is pending.
5. Finalize document statistics and ANNOTATED state, then stream final BRAT/TSV/
   statistics/manifest exports from those same verified publications.

Model failures preserve other members. No-match lexical results are valid.
A document with no successful NER member is FAILED; its original remains
readable. A preview has PROCESSING status and can already contain mentions or
normalized concepts. `annotated_documents` and `progress_percent` still count
**finished documents**, not partial previews or elapsed time. NER cards show
member progress independently. Provisional mention counts include previews, and
active progress explicitly announces available partial results.

The existing NerLabSession/HubSession and upstream encoders, logits decoding and
BIO reconstruction remain in use. Each model processes successive batches without
alternating model order, avoiding revisiting every model for each corpus batch.
No entire corpus text/logit tensor is retained in RAM. Intermediate per-document
raw member spans are stored privately on disk for merging/dependent tasks and
restart recovery; this adds disk writes compared with final-only publication.
Final records discard the temporary member checkpoint state. This change makes
no numerical performance or clinical-accuracy claim.

## Atomic snapshots and live viewer

`published/<document_id>/artifact.json` contains the merged canonical annotations,
input hash, model snapshot, provenance and a random publication revision. While
incomplete, `complete=false` and `state` contain member outcomes and completed
normalization categories. Legacy records without `complete` remain final records.
The first publication renames a private building directory into place. Later
publications replace individual files atomically; artifact readers always see a
complete JSON snapshot. ANN and JSON are each atomic; separate HTTP requests can
observe adjacent valid revisions. Original text is never duplicated or changed.

`documents.updated_at` and progress `publication_revision` notify the viewer even
when annotation counts stay constant, as during normalization. The viewer opens
pending documents, polls live publications, retains document/chunk position and
filters, and updates a selected mention's normalization. Annotation pagination
returns a revision; if the revision changes between pages the viewer restarts
that read instead of mixing pages from different snapshots. An empty ANN download
is available before any annotations exist. Full-corpus downloads appear after
packaging; individual documents and partial ANN snapshots are available earlier.

## Recovery, failure and deletion

A crash before atomic replacement leaves the previous snapshot readable. A crash
between file replacement and the DB count update leaves a valid durable snapshot.
Recovery verifies input SHA-256, exact surfaces and the pinned model/options
snapshot, restores per-member counts and skips already completed member/document
or normalization-category/document work. Fully published documents are not
counted twice. Missing/corrupt artifacts are reprocessed. Changed model,
statistics-tokenizer or terminology snapshots fail rather than mixing contracts.
`MAX_ATTEMPTS` remains bounded. Finished FAISS indexes are reusable; an interrupted
cold index build itself still restarts from scratch through native ner_lab.

The worker logs `job_interrupted` with a sanitized reason, child exit code and
configured `timeout_seconds`. A timeout records `JobTimeout` on unfinished model
cards; already completed member cards retain their completed state. The configured
`JOB_TIMEOUT_SECONDS` remains a whole-child deadline, including first-use index
building and shutdown. Raising it is an explicit deployment choice, not a hidden
change. The attached historical log ended with a generic `success=False`; it did
not identify a cause, so timeout remains a plausible explanation, not a diagnosis.

FAILED jobs retain readable partial snapshots until their terminal retention
expires. No complete corpus export is advertised for a failed job. Previously
failed pre-0.10 jobs with no publications cannot reconstruct NER predictions
from progress logs; they need a new submission. They can still expose retained
originals. Restart/drain both web and worker when upgrading.

Publication and deletion share a filesystem lock plus the job content-version
guard. Deletion immediately removes originals, snapshots/checkpoints, annotations
and downloads; stale inference cannot republish deleted content. Repackaging
surviving final documents reuses annotations and requires no current dictionary.
My documents selection/deletion is unchanged by this release.

A 72-hour availability deadline starts at terminal completion, not while queued
or processing. Cleanup removes originals, publications, intermediate files,
exports and viewer caches. Native TextMeasurements/AnnotationMeasurements retain
canonical aggregate statistics; no statistical inference runs on viewer requests.
