# Audited ner_lab integration for V3

Pinned source: nlp4bia-bsc/ner_lab commit
8640d4797b081a5f6b66d9b45c11269542a79a26, package lab 0.1.0. Reviewed README,
pyproject, docs/core and docs/ner contracts, docs/dev design/style decisions,
src/lab/core corpus/segmentation/sentences/statistics and src/lab/ner/inference,
loading/encoding/prediction plus verification fixtures. No core library change.

The public `predict_entities` API loads a saved checkpoint per invocation and
returns InferenceResult.spans/metrics/manifest/paths. Its span table is filename,
label, start_span, end_span, text, score. The legacy NerLabAdapter remains available
and is the reference used to verify the V3 production session's actual outputs.

NerLabSession now composes upstream load_model, encoder_from_description,
read_documents, predict_logits and decode_spans directly. It passes the same
saved encoding, require_target_label=False, batch size, device, min_score and
pad_to_multiple_of=8 as the public raw-text path. No gold is supplied or scored.
A bounded LRU retains model/tokenizer objects across document microbatches within
one supervised job child. Checkpoint path/digest/device identify cache entries;
versions/options are snapshotted at admission. GPU memory can constrain capacity;
cache eviction/reloads are intentional when the selected model set is larger.

These lower-level module functions/classes are real pinned upstream code, not an
official stable InferenceSession API. Upgrades must review their signatures and
rerun session/public-API equivalence tests. An upstream public reusable session
would simplify future maintenance. No arbitrary global monkeypatch of model loading
or custom scientific engine is used. Callable/custom architectures/strategies
remain subject to the original administrator preflight restrictions.

encoding.json is authoritative for architecture, target, language and the complete
window configuration. No manual 512-token limit, document truncation or simplistic
sentence regex is introduced. Upstream split_into_sentences/sentence_token_ranges/
tokenize_document/merging/windowing/decoding retain PySBD, bundled Punkt or ICU
routing and Unicode word definitions. CRF models may require the original backbone
in a pre-provisioned local cache. Offline flags are set before tokenizer/model use;
public requests never select remote model URLs or download arbitrary checkpoints.

All input bytes (including CRLF, Unicode/BOM/combining characters) remain unchanged.
Mapping keys are original relative TXT paths including extension. Canonical offsets
are Python Unicode code points, inclusive start/exclusive end. Every entity must
round-trip exactly; no fuzzy offset repair. Invalid prediction batches fail without
publishing partial-model documents. Native window deduplication remains upstream;
cross-model merge keeps the highest score for exact document/label/start/end
matches while preserving different labels and legitimate crossing/nesting.

StreamingStatistics reuses native TextMeasurements and AnnotationMeasurements
with one loaded reference fast tokenizer. It calls their add/row methods, so
vocabulary, weighted MATTR, quantiles, mention complexity and label distributions
retain native definitions. Public compute_text_stats/compute_annotation_stats are
kept as a reference and their equality with streamed measurements is tested.
The lower-level statistics classes were already used by v2 for document counts;
the revision pin remains important. Undefined native values become strict-JSON null.

The reference is configured local statistics_model or the first selected checkpoint.
Its effective path/digest is snapshotted and checked on restart; incompatible
statistics cannot mix. Tokens from different model vocabularies are never summed.
Per-document native counts publish with validated spans. Provisional sums are
identified as annotated-document-only; final native corpus figures are computed
once at completion, never recomputed by normal viewer reads. No precision/recall/
F1 is displayed without gold. Operational timings/counters remain separate.

The same validated spans feed canonical annotation JSON, ANN, TSV and native stats.
BRAT normalizes tabs/newlines only in its one-line surface display; offsets/TXT
remain original. The browser maps code points explicitly to UTF-16 DOM ranges.
Empty text is rejected, and no-window inference errors are explicit failures.
All-model document publication and partial/final semantics are detailed in
INCREMENTAL_PROCESSING.md. Real tiny-BERT CPU tests validate mechanics/equivalence;
no clinical accuracy or GPU capacity is claimed.
