# Audited ner_lab integration

Source audited locally: nlp4bia-bsc/ner_lab commit
`8640d4797b081a5f6b66d9b45c11269542a79a26`, package `lab` 0.1.0.
Reviewed README, pyproject, docs/core/library.md and prepare-dataset.md,
docs/ner/predict-entities.md, src/lab/core corpus/spans/brat/segmentation/sentences/
stats modules, src/lab/ner/inference predict/loading/prediction/io, encoder and
trainer descriptions, verification README/fixtures/verify_inference. The core
library was not modified.

## Contracts reused

`lab.ner.predict_entities(model_dir, documents, output_dir, batch_size=16,
device='auto', min_score=0.0)` takes a document mapping, canonical corpus or input
directory. Returns `InferenceResult.spans` (filename, label, start_span, end_span,
text, score), `.metrics`, `.manifest`, `.paths`. The adapter calls it once per
selected model with all documents, so it loads a checkpoint once per model/job,
not once per document. No long-lived model cache is added. Paths returned by
ner_lab are private and are never exposed through public API/manifests.

`lab.core.span_dataframe(spans, scored=True)` builds the canonical deduplicated
span table. `build_corpus(documents, annotations, on_mismatch='documents')` includes
documents without predictions and validates their exact entity surfaces. Its
built-in `validate_corpus` is retained. `compute_text_stats(frame, base_model,
language)` and `compute_annotation_stats(frame, base_model)` each return a one-row
DataFrame. Conversion via pandas JSON maps undefined native NaNs to null.
Public write_stats/write_manifest are available; this app writes the combined
operational/native JSON envelope itself to enforce strict JSON and strip private
locations. It does not invent names for native statistical fields.

For per-document statistics, the minimal adaptation reuses the upstream
`TextMeasurements.add/row`, `AnnotationMeasurements.add` and `load_tokenizer`
classes/functions from lab.core.stats modules. These are lower-level, unexported
APIs at the pinned revision and must be reviewed when upgrading. They let us reuse
one tokenizer across 1,000 documents while preserving identical definitions.
Calling the public aggregate functions once each and loading the document
statistics tokenizer once gives three tokenizer loads per job, not thousands.

`describe_sentence_segmenter(language)` records provenance. Internally ner_lab
uses split_into_sentences, split_into_words, tokenize_document,
sentence_token_ranges and its window strategy. Sentence routing is PySBD for its
supported language table, bundled Punkt for other listed languages, ICU for other
ISO 639-1 languages. Unicode UAX #29 word boundaries include punctuation spans;
stats `words_of` counts only spans containing letters/digits, lowercased for
vocabulary. Tokens are model subwords without special tokens. Sentence counts use
the exact native TextMeasurements definition. These operations, merging sentence
ranges and rebuilding model windows are never reimplemented here.

## Text and offsets

Input UTF-8 bytes are preserved, including CRLF, BOM, accents and emoji. Decode
without universal newline translation. The library accepts a dict mapping each
original relative `.txt` path to text; this avoids directory glob/stem collisions
and means no lossy internal-ID translation is needed. Annotation offsets are
Python Unicode code-point indices, zero-based start inclusive/end exclusive,
not byte indices or JavaScript UTF-16 code units.

Every prediction must satisfy `original_text[start:end] == predicted_text`, with
valid bounds, known filename, expected label and finite confidence when supplied.
Any invalid prediction fails the whole job. No fuzzy repair is attempted.
The upstream decoder already deduplicates overlapping-window predictions at the
highest score. Cross-model aggregation also deduplicates exact document/label/
start/end keys at the highest confidence, retaining overlaps/different labels and
sorting deterministically. BRAT IDs restart at T1 for each document. BRAT surface
forms replace tabs/newlines with spaces as required by its line format; offsets
and exported original TXT remain unchanged. TSV uses standard quoted fields and
preserves original entity surfaces.

## Models and windows

Saved `encoding.json` contains model architecture/base and the complete encoding
(language, target label, strategy, vocabulary, windows, overlaps). Inference reads
it through upstream load_model and encoder_from_description, without manually
setting 512-token limits, truncation, segmentation or window offsets. The
administrator preflight uses the same loader and encoder constructor offline.
Checkpoint directories must include weights, encoding.json and a saved fast
tokenizer. Their full content digest is validated and snapshotted into jobs.

Callable/custom architectures or window strategies not serializable by upstream
need a future explicit adapter; they are rejected by preflight. CRF models may
need their original backbone present in the local Hugging Face cache because the
upstream loader reconstructs it from the saved base_model. Provision that cache
in advance, validate it in the runtime image, and retain offline mode. There is no
public model URL/path input and no model download during inference.

Public aggregate token counts use one explicit reference tokenizer: configured
local statistics_model, otherwise first selected checkpoint. Counts from different
model tokenizers are never added together. Native token/segmenter definitions and
versions accompany the stats. Operational counts/elapsed times are a separate JSON
namespace. No precision, recall or F1 is computed for raw, unannotated inputs.

Empty/whitespace documents are rejected at admission because build_corpus rejects
them. A nonempty document that produces no windows can still fail predict_entities;
that error is a failed job, never simulated success. Files without mentions get an
empty ANN. Upstream writes TSV/parquet intermediates; they remain private and are
deleted after successful packaging or failed execution. Installed NER extras are
large because upstream couples training dependencies with inference.
