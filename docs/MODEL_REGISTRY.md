# Model registry operations

Source: `catalog/models.yaml`, configurable via MODEL_CONFIG_PATH. API and worker
load it independently; changes require coordinated restart after draining the
queue. Add language codes/display names and entity mappings to YAML, not HTML.

Entity fields: display_name, optional description, model_id (stable safe identifier),
version, enabled, model_dir (local admin-controlled path), min_score [0,1] and
batch_size [1,1024]. Entity labels must be BRAT-safe identifiers. No unvalidated
model becomes available merely because enabled is true.

Run `python -m scripts.validate_models` with the real NLP environment and identical
model paths/cache mounts used at runtime. Preflight checks saved weights,
encoding.json, fast tokenizer, ISO language routing, target label/language,
actual model initialization and encoder reconstruction. Its JSON receipt maps
language:label to model ID and SHA-256 of the checkpoint's complete directory.
Keep that receipt local, writable only by administrators and untracked in Git.
The receipt is not a cryptographic attestation against malicious administrators;
models and YAML are trusted deployment inputs.

At API startup and worker execution the checkpoint digest must match. Each job
snapshots model identity, digest and options; a changed configuration fails the
job rather than silently selecting a different model. Do not mutate checkpoint
directories in place. Stage versions in new directories, drain old jobs, validate
new configuration, and restart components. A web catalog is a startup snapshot;
if a model disappears after startup the worker fails safely, so use readiness and
operational monitoring during maintenance.

statistics_model is an optional local reference tokenizer directory. Without one,
the first requested checkpoint supplies the tokenizer. Native aggregate stats load
the reference tokenizer twice; per-document stats load it once more and reuse it.
It must be a saved fast tokenizer. Counts remain labeled as reference-tokenizer
counts, not sums across incompatible subword vocabularies.

Run preflight inside Docker with INSTALL_NLP=true, mounting `/models` read-only
and `catalog` temporarily writable for receipt generation. The default image has
no Torch and cannot initialize a model. Disabled entities remain visible with
“Not available for this language”; no available entities means no submission.
Callable/custom architecture/strategy and ensemble orchestration require explicit
future adapters; no arbitrary executable configuration is exposed publicly.

Phase 2 requires no catalog migration. The form and explorer share configured
labels; new entities need no frontend code. Display colors are deterministic aids,
not label identities. Viewer filters never change model selections or saved spans.

V3 sessions key cached checkpoints by path/digest/device and retain at most
MAX_LOADED_MODELS per job child. The saved encoding/threshold/options are unchanged.
Reference tokenizer path/digest is also snapshotted; changes fail rather than mix
statistics on restart. Increase cache capacity only after measuring RAM/VRAM; a
larger selected model set may reload checkpoints between microbatches. Alternating
traversal order preserves recent cache entries without changing predictions.
