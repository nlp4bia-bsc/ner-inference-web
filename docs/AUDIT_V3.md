# V3 audit (baseline 9c95bb5)

Executed baseline: 94 tests passed in 51.77 seconds, including actual tiny-BERT
CPU inference and browser viewports. Current implementation already has a native
overlap viewer, shared span contracts, modular routers/services, actual /ner
prefix support and 72-hour defaults. These are verified, not missing features.
SQLite WAL + flock is deliberately single-host; there is no Redis/RQ dependency.

P0: whole-job publication and in-memory corpus processing prevent early viewing;
progress is terminal-only. HTTP admission buffers the entire multipart body and
then reads all files into another mapping. There are no pasted-text inputs,
document-state persistence or partial-result semantics. Preserve original offsets,
all-model completion, old tokens/deadlines and final-export integrity during changes.

P1: admission scans terminal directories while holding a SQLite write lock and
reserves worst-case expanded corpus space for tiny jobs. The public ner_lab
predict_entities loads a checkpoint for each invocation; naive per-document calls
would regress loading costs. Add a version-pinned job-scoped bounded session using
upstream loading/encoding/predict/decode pieces, not a new scientific engine.

P1 UI: add real persisted progress, reconnect/backoff polling, server-synchronized
countdown, accessible acceptance/completion dialogs and three explicit input modes.
Retain the tested sweep-line overlap renderer and original-code-point coordinates.

P2: CI, reproducible synthetic concurrency/memory/timing benchmarks, cached native
statistics and artifact accounting. No GPU or real biomedical checkpoint benchmark
can be claimed here. Results and implementation decisions are appended after runs.

## Implemented and executed

The source-neutral input contract, disk-spooled admission, additive migrations,
per-document persistent states, bounded native inference session, atomic publication,
streaming statistics/exports, partial-result semantics, server-clock progress UI,
dialogs, file tree, synchronized table and CI workflow have been implemented.

Regression runs retain the existing real CPU inference, offsets, model registry,
BRAT/TSV, rate limit, prefix, retention, private-link and browser cases. Additional
checks cover all-model publication, crash windows, old schema/token/deadline
migration, real concurrent HTTP admission, paste bytes/CRLF, quota rejection and
clock-skew/expiry in the browser. Exact final totals are in VERIFICATION.md.

Measured bottleneck changes: traced Python ingestion peak fell from 32.29 to 1.33
MiB for the 1,000x16KiB fixture; v3 elapsed admission includes persistence and is
not claimed faster than the old pure loader. Microbatch and actual tiny-BERT
session/renderer results are recorded in PERFORMANCE_V3.md with reproducible JSON.
Real clinical checkpoints, GPU sizing, true external TCP load/soak tests and BSC
production deployment remain P2 validation tasks, not claimed completed benchmarks.
