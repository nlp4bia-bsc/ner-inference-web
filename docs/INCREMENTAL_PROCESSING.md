# V3 incremental inference and recovery

Each accepted source becomes a source-neutral reference: document_id, original
relative path, source_type (PASTED_TEXT/TXT_UPLOAD/ZIP_ENTRY), content_reference,
size_bytes and PENDING status. Original bytes remain in private input files.
SQLite holds document states and metadata, never clinical text or logits.

The existing lifetime-exclusive supervisor still runs one job child at a time.
INFERENCE_DOCUMENT_BATCH_SIZE defaults to 32. A microbatch loads only its own input
bytes/texts. Every selected model runs over that complete microbatch using its
saved encoding.json. Only after all models finish, predictions round-trip against
the original text and the merge is validated can a document become ANNOTATED.
An inference/offset error fails the affected microbatch, not earlier publications;
subsequent microbatches are attempted. There is no partly modeled document.

A job-scoped bounded NerLabSession composes the exact upstream load_model,
encoder_from_description, read_documents, predict_logits and decode_spans pieces.
No segmentation, window generation, logits decoding or offset reconstruction is
reimplemented. The cache key includes checkpoint path/digest/device; its default
capacity is two checkpoints. Model traversal order alternates between microbatches
so the last loaded models can be reused when not all checkpoints fit. Results are
independent of model traversal order and merged deterministically. For model sets
larger than the cache, some reloads remain unavoidable; tune capacity only after
measuring RAM/VRAM. The cache is cleared at job end and the child process exits.

This is a version-pinned adapter over lower-level upstream modules, not a claim of
a new official ner_lab session API. tests/test_real_session.py compares its actual
spans/scores with public predict_entities and verifies a warm call avoids loading.
A future upstream public InferenceSession would remove this adapter maintenance
burden. Callable/custom encodings remain subject to existing preflight rejection.

Native TextMeasurements/AnnotationMeasurements and one reference tokenizer collect
statistics without a full-corpus mapping. Per-document statistics publish with the
document. Final vocabulary/MATTR/quantile statistics come from the native running
measurements, not averages of per-batch percentages. Their equality to the public
aggregate functions is tested. Reference tokenizer path/digest is snapshotted at
admission and checked on execution/retry; incompatible statistics are not mixed.
No statistical work is repeated on normal viewer requests.

Publication order:

1. Persist PROCESSING for the current document batch.
2. Run all models, merge and validate original-coordinate spans.
3. Compute native document statistics.
4. Write artifact.json + ANN in a private .building directory.
5. Atomically rename that document directory into published/{document_id}.
6. Commit ANNOTATED and counts/statistics to SQLite.
7. Serve it through the token/expiry-guarded document APIs immediately.

A crash before rename leaves an invisible incomplete directory. A crash after
rename but before SQLite commit leaves a complete artifact; restart verifies its
checkpoint/options snapshot, input SHA-256 and exact surfaces, then registers it
idempotently. Published documents are not counted twice. Missing/corrupt artifacts
are reprocessed; changed model/tokenizer snapshots fail safely rather than reuse
incompatible annotations. Interrupted PROCESSING rows return to PENDING, while
verified ANNOTATED rows survive controlled retries. MAX_ATTEMPTS remains bounded.

After document processing the stage becomes PREPARING_DOWNLOADS. Packaging streams
original files and the very same published ANN/span records into BRAT/TSV/JSON/ZIP,
without rebuilding a corpus mapping. COMPLETED means every document and required
artifact succeeded. COMPLETED_WITH_ERRORS means validated subset exports exist;
attachments are named *_partial and the manifest lists failed documents. FAILED
means no final batch export is offered; already published valid documents remain
available individually and explicitly partial until terminal expiry. Annotation
progress excludes failed documents and is not elapsed-time progress.

A 72-hour deadline is created at terminal completion, never while queued or
processing. Previous links/deadlines are preserved. Cleanup removes the entire job
root, including originals, publications, incomplete artifacts, final exports and
viewer caches. Partial states never bypass capability or expiry checks.
