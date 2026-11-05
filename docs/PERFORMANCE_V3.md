# V3 measurements (synthetic data, CPU only)

Reproduce from the repository with development/NLP dependencies installed:

```sh
python -m scripts.benchmark_v3 --real-model
python -m scripts.benchmark_viewer
```

The first command creates isolated subprocesses for each case, using 1,000 UTF-8
TXT documents of 16 KiB in a ZIP_STORED archive. Hardware reported: Linux x86_64,
3 visible CPUs, Python 3.12.14, kernel 6.18.57. No GPU was used. Raw machine-readable
results are in benchmarks/v3-mechanics.json and benchmarks/v3-viewer.json.

| Ingest path | Peak traced Python allocations | Time |
|---|---:|---:|
| Baseline 9c95bb5 loader | 32.29 MiB | 0.86 s |
| V3 stream admission, batch setting 32 | 1.33 MiB | 1.46 s |

This measures a roughly 24x reduction in traced ingestion allocations for this
fixture, not a universal RAM promise. Baseline measures the old pure in-memory ZIP
loader; v3 also performs disk writes and persistent admission. Their elapsed times
are not equivalent HTTP end-to-end benchmarks. Admission is intentionally not
claimed faster. RSS includes Python, FastAPI and the case's whole process, not
only worker allocations: 86.1 MiB baseline and
67.4 MiB for batch 32. Tracemalloc excludes native allocations and GPU memory.

| Documents per microbatch | First published document | Whole worker case | ZIP generation | Progress HTTP p95 | List response |
|---:|---:|---:|---:|---:|---:|
| 8 | 0.067 s | 5.352 s | 0.178 s | 18.4 ms | 21.4 ms |
| 32 | 0.093 s | 2.155 s | 0.171 s | 19.8 ms | 46.3 ms |
| 64 | 0.067 s | 1.620 s | 0.196 s | 23.8 ms | 19.9 ms |

These are controlled-predictor/statistics mechanics results. They include actual
SQLite publication, filesystem artifacts, packaging and ASGI queries during
processing, not neural throughput. Publication intervals and separate ZIP timings
are recorded in JSON. The 32-document default remains configurable; these numbers
do not establish an optimal GPU or clinical-model batch size. This is a local
single-run comparison, not a sustained multi-user load certification.

A separate randomly initialized tiny BERT used the actual pinned ner_lab inference
pieces on CPU. Cold checkpoint loading was 23.23 ms; the subsequent cache lookup
was 3.07 microseconds. Cold/warm inference-call totals were
68.33/14.76 ms in the recorded run. Imports/process startup are outside that loading timer. These tiny
fixture costs must not be extrapolated to multi-GB biomedical checkpoints. Native
encoding timing includes tokenization/segmentation/window generation; those are
not replaced or separately approximated for profiling.

Renderer isolation (actual spans.js algorithm, synthetic overlaps, 1440x900):

| Annotations | Atomic segments | Segment/lane calculation | Plain DOM/layout |
|---:|---:|---:|---:|
| 100 | 189 | 4.2 ms | 20.0 ms |
| 1,000 | 1,785 | 13.3 ms | 16.5 ms |
| 3,000 | 3,491 | 47.8 ms | 44.8 ms |

The renderer microbenchmark excludes application CSS, HTTP and inference; actual
application behavior is separately exercised in Chromium across eight viewports.
Its about:blank benchmark harness evaluates trusted local source and never weakens
the application's CSP. Clinical data is never used.

Concurrency tests issue eight simultaneous actual ASGI requests on distinct client
IPs/emails, assert all admissions persist and FIFO claims match sequence order.
Single-worker locking, native CPU inference with HTTP polling, bounded upload
leases, quota rejection and partial-result recovery are tested separately. No
real external-user TCP load generator, GPU capacity or BSC soak test is claimed.
