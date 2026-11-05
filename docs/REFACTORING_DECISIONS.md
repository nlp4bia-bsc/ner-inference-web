# Phase 2 refactoring decisions

Baseline: work at 842f66f; 71 tests passed in 22.57s before code changes.
Audited all application modules, tests, README/configuration and existing docs,
plus ner_lab docs/dev/DESIGN.md, CODE_STYLE.md, DECISIONS.md, core/inference
contracts at the pinned revision. No ner_lab code was changed.

Previously app/main.py owned middleware, validation, routes, file admission,
queries and private artifact lookup. It now only composes application resources,
HTTP adapters and the cleanup lifecycle. Existing external routes and field names
remain compatible. Test-only monkeypatches for document ingestion now target
app.services.jobs.load_documents, its new owner.

- api/: routers for jobs, catalog/health, downloads, documents and web pages;
  request/job response schemas; private HTTP error and admission policies.
- services/jobs.py: admission and status use cases, independent of FastAPI.
- services/pipeline.py: NLP/statistics/export/viewer publication orchestration;
  worker.py retains supervision and its existing test/import compatibility seam.
- domain/annotations.py: original-coordinate surface validation and canonical
  annotation schema. Visualization and exports consume validated spans without
  flattening overlapping annotations or replacing model confidence.
- visualization/: typed API contracts and private indexed document repository.
- services/exports/: BRAT and TSV writers separated from package orchestration;
  services/export.py remains the compatible package entry point.
- Existing config.py/db.py/storage.py remain cohesive infrastructure modules.
  Moving them merely to imitate a directory tree would add churn without a new
  responsibility. Persistence rows remain private dicts, not API annotation models.

The actual v1 queue is SQLite WAL with a lifetime-exclusive sequential worker,
not Redis/RQ/PostgreSQL. Preserve this supported single-host architecture rather
than introduce a queue migration during a viewer/UI change. Distributed workers
still require a separate migration. No fake Redis/RQ services or credentials have
been documented as functional dependencies.

No database schema change is needed for viewer artifacts. Completed v1 jobs can
backfill a private index from their original TXT/TSV on first viewer access under
a per-job filesystem lock. The configured default retention is now 72 hours;
scripts.migrate_retention explicitly updates only still-unexpired terminal jobs.
Expired jobs are never revived. Deploy API/worker together, draining active work.

No large frontend dependency/build chain: ES modules, native DOM, CSS Grid and
server templates. This keeps the frontend independent of NLP and avoids remote
assets/telemetry. Review new API/domain/renderer tests before changing contracts.
