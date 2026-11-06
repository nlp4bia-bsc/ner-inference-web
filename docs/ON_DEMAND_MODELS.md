# On-demand models · 0.6.0

The configured catalog is the authority for model choices. A repository does not
need to be active, predownloaded, loaded into memory or approved by an offline
preflight before a user can submit it. All 48 configured Hub repository entries
are selectable in their configured languages. Entries without any repository or
local source remain unavailable; no checkpoint URL is invented for them.

## First use and warm use

1. Listing/selecting models performs no network request and loads no weights.
2. The supervised worker enters PREPARING_MODELS on the first job.
3. `huggingface_hub.snapshot_download` resolves repository metadata. The worker
   checks required download space and resolves an immutable commit before fetching
   weights/config/tokenizer files. No model is compiled, trained or converted.
4. The standard Hub snapshot cache is stored under `/data/model-cache/hub` in
   Docker's shared private `ner-data` volume. Warm jobs find that snapshot without
   another network request. Cache state refreshes in the catalog without restart.
5. `resolved-models.json` inside the private job pins each exact repository and
   commit. A resumed job retains that revision even if a branch later changes.
6. Each job keeps up to MAX_LOADED_MODELS weights/tokenizers in memory. The worker
   child exits after the job, releasing memory; disk cache survives jobs, 72h result
   expiry and service restarts. Cache files contain models, not clinical inputs.

The UI distinguishes Download on first use and Cached / ready to load. Cached
does not mean continuously resident in RAM. `MODEL_CACHE_DIR` can choose another
private shared Hub cache path. An explicit catalog `revision` can be a commit or
tag; absent one, the cached main revision is reused. To intentionally update a
model, change its revision or refresh its Hub cache between jobs. Drain queued
jobs before changing their registered model contracts.

## Runtime formats and original coordinates

Native ner_lab exports with `encoding.json` retain the existing native loader.
Standard Hugging Face token classifiers use local-only AutoConfig/AutoTokenizer/
AutoModelForTokenClassification after snapshot preparation. Custom remote code is
disabled. The worker rejects non-token-classifier heads, generic/non-BIO labels,
invalid indexes and missing/mismatched weights; it never silently creates an
untrained head to make a backbone appear to perform NER.

Windows, prediction and span decoding use the pinned ner_lab building blocks.
Fast tokenizers are required. Every result must round-trip against the untouched
original Unicode text with half-open code-point offsets before publication.

Original model labels remain in provenance. Existing declared mappings are used;
if a checkpoint is bound to a single canonical category, its actual BIO labels
can map to that category (e.g. ENFERMEDAD to DISEASE). If several canonical
categories are registered, unmapped labels cause a model-level error rather than
a guessed mapping. Same-category/equal-range votes consolidate with all sources,
scores and original sublabels retained as before.

Custom multi-head models or annotation-dependent classifiers need a compatible
runtime adapter. They remain selectable if configured, but unsupported execution
is reported as that model's error. A `requires` dependency is honored; a dependent
model never receives raw text as a substitute for missing upstream annotations.

## Failures and debug

Model preparation and prediction failures are isolated. A failed invocation's
predictions, including malformed offsets/scores, are discarded. Other models in
the batch continue. Zero legitimate mentions from a successful model remain a
valid result; zero successful models never produce fabricated empty success.
Previously successful published batches retain their valid predictions.

Mixed outcomes finish COMPLETED_WITH_ERRORS, with `_partial` downloads and
`manifest.partial=true`, even if every document has some valid predictions.
`summary.failed_models`, `summary.model_errors` and manifest model errors identify
the affected models. If all models fail, the job fails and no final export is
offered. Per-document incremental publication and retention/ownership still apply.

Private worker logs contain job ID, model ID, phase, exception type, any HTTP
status available through exception causes, and source file/function/line frames.
`jobs/<job-id>/model-errors.json` records safe structured details. No exception
message, patient text, token, Authorization header or raw request body is logged
by this error handler. Debugging does not require making results public.

## Runtime/deployment

```sh
docker compose build web worker
docker compose up -d
```

The web image contains HTTP dependencies. The worker image contains pinned CPU
inference libraries by default (`INSTALL_NLP=true`, `NLP_PROFILE=cpu`). Neither
build downloads weights. A library/runtime image build is separate from a model
download. Adding a catalog repository does not require rebuilding these libraries;
restart services to reload catalog changes. GPU requires the deployment's device
grant plus the GPU library profile; it is not enabled by a model-cache flag.

Defaults: `MODEL_LOADING_MODE=on_demand`, `HF_HUB_OFFLINE=0`,
`TRANSFORMERS_OFFLINE=0`, `HF_HOME=/data/model-cache`. Set HF_TOKEN only in the
worker's private environment for gated/private repositories. Optional offline mode
can reuse complete cached snapshots; uncached repositories then fail explicitly.
`MODEL_LOADING_MODE=validated_local` retains the earlier receipt-only workflow for
deployments that explicitly need it. Its enabled/schema-review/receipt rules do
not govern the on-demand mode.

Outbound HTTPS must allow Hugging Face metadata and its actual download/CDN/Xet
hosts. TLS verification remains enabled; proxy installations must supply their
trusted CA to the runtime as appropriate. This managed session's policy denies
`https://huggingface.co` at CONNECT with 403. Real public clinical repositories
could not be downloaded here; no policy bypass or clinical accuracy claim is made.

## Executed acceptance checks

Real Hugging Face client requests to an isolated local HTTP Hub fixture download
a small randomly initialized BERT token classifier, cache it, resolve its commit,
then reuse it with no network requests. Native CPU inference/Unicode offset
roundtrips and warm second-job reuse pass without receipts or `enabled:true`.
A 404 model does not cancel a working classifier. Separate cases cover malformed
model output, all-model failure, privacy-safe debug records, all 48 configured
repositories, and actual root/prefix browser submission of an uncached choice.
These are synthetic mechanics tests, not biomedical performance evaluation.
Full suite/build/runtime evidence is recorded in [VERIFICATION.md](VERIFICATION.md).
