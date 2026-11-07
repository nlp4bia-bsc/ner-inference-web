"""Model-first NER and category-first normalization over durable document snapshots."""

import shutil

from app.persistence.job_locks import JobContentChanged, check_content_version, job_lock
from app.services.inference import merge_predictions
from app.services.publication import publish, read_publication


class DocumentPhases:
    def __init__(
        self,
        *,
        job,
        settings,
        db,
        root,
        rows,
        snapshot,
        progress,
        reporter,
        budget,
        engine,
        normalizer,
        failed,
        finalize,
    ):
        self.job, self.s, self.db, self.root = job, settings, db, root
        self.rows, self.snapshot = rows, snapshot
        self.progress, self.reporter, self.budget = progress, reporter, budget
        self.engine, self.normalizer = engine, normalizer
        self.failed, self.finalize = failed, finalize

    def batches(self):
        size = self.s.inference_document_batch_size
        for offset in range(0, len(self.rows), size):
            yield offset // size + 1, self.rows[offset : offset + size]

    def load(self, row):
        with job_lock(self.s, self.job["id"]):
            check_content_version(self.db, self.job)
            try:
                record = read_publication(self.root, row, self.snapshot)
            except (OSError, ValueError, KeyError):
                record = None
            raw = (self.root / "input" / row["filename"]).read_bytes()
        return raw, record or {
            "spans": [],
            "models": [],
            "state": {"members": {}, "normalizers": {}},
        }

    def save(self, row, raw, record):
        stats = {
            "filename": row["filename"],
            "characters": len(raw.decode("utf-8")),
            "entities_total": len(record["spans"]),
            "processing_status": "PROCESSING",
        }
        with job_lock(self.s, self.job["id"]):
            check_content_version(self.db, self.job)
            count, labels = publish(
                self.root,
                row,
                raw,
                record["spans"],
                stats,
                self.snapshot,
                record["models"],
                budget=self.budget,
                complete=False,
                state=record["state"],
            )
            self.progress.preview(self.job["id"], row["document_id"], count, labels, stats)

    def ner(self, models):
        for model_index, model in enumerate(models):
            self.progress.stage(self.job["id"], "INFERENCE")
            for batch_index, batch in self.batches():
                loaded = [(row, *self.load(row)) for row in batch]
                active = [
                    item for item in loaded if model["model_id"] not in item[2]["state"]["members"]
                ]
                if not active:
                    continue
                texts = {row["filename"]: raw.decode("utf-8") for row, raw, _ in active}
                self.progress.mark(
                    self.job["id"], [row["document_id"] for row, _, _ in active], "PROCESSING"
                )
                self.reporter.start_batch(model["model_id"], batch_index, len(active))
                if hasattr(self.engine, "on_progress"):
                    self.engine.on_progress = self.reporter.callback(model["model_id"])
                try:
                    if model.get("task", "ner") != "ner" or model.get("requires"):
                        if not hasattr(self.engine, "classify"):
                            raise ValueError("No adapter for the selected dependent task")
                        inputs = {
                            identity: [
                                span
                                for _, _, record in active
                                for span in record["state"]["members"]
                                .get(identity, {})
                                .get("spans", [])
                            ]
                            for identity in model["requires"]
                        }
                        if any(
                            identity not in record["state"]["members"]
                            or "spans" not in record["state"]["members"][identity]
                            for _, _, record in active
                            for identity in model["requires"]
                        ):
                            raise ValueError("Required upstream model failed")
                        spans, meta = self.engine.classify(model, texts, inputs, self.s.device)
                    else:
                        spans, meta = self.engine.predict(
                            model,
                            texts,
                            self.root / "building" / f"model-{model_index}",
                            self.s.device,
                        )
                    meta = {**meta, "model_id": model["model_id"]}
                    resolved = {
                        **model,
                        "label_mapping": meta.get("label_mapping", model["label_mapping"]),
                    }
                    merge_predictions(texts, [(resolved, spans)])
                    member = {
                        k: resolved[k]
                        for k in ("model_id", "label", "version", "label_mapping")
                        if k in resolved
                    }
                    success = True
                except JobContentChanged:
                    raise
                except Exception as exc:
                    meta = self.failed(model, exc, "INFERENCE", len(active))
                    success = False
                for row, raw, record in active:
                    outcome = {"metadata": meta}
                    if success:
                        outcome.update(
                            model=member,
                            spans=[span for span in spans if span["filename"] == row["filename"]],
                        )
                    record["state"]["members"][model["model_id"]] = outcome
                    record["models"].append(meta)
                    record["spans"] = merge_predictions(
                        {row["filename"]: texts[row["filename"]]},
                        [
                            (value["model"], value["spans"])
                            for value in record["state"]["members"].values()
                            if "spans" in value
                        ],
                    )
                    self.save(row, raw, record)
                    if model_index == len(models) - 1 and self.normalizer is None:
                        self.finalize(row, raw, record)
                if success:
                    self.reporter.complete_batch(model["model_id"], len(active))
                shutil.rmtree(self.root / "building", ignore_errors=True)
        # NER checkpoints need no resident GPU model during normalization.
        if hasattr(self.engine, "close"):
            self.engine.close()

    def normalize(self):
        if not self.normalizer:
            return
        self.progress.stage(self.job["id"], "NORMALIZATION")
        entities = {
            row["entity"]
            for row in self.normalizer.catalog.snapshot(
                self.job_payload["language"], self.job_payload["entities"], self.normalizer.method
            )
        }
        ordered = [
            entity
            for entity in ("DISEASE", "MEDICATION", "PROCEDURE", "SYMPTOM")
            if entity in entities
        ]
        for entity_index, entity in enumerate(ordered):
            model = {"model_id": f"normalizer-{self.job_payload['language']}-{entity}"}
            for batch_index, batch in self.batches():
                loaded = [(row, *self.load(row)) for row in batch]
                active = [item for item in loaded if entity not in item[2]["state"]["normalizers"]]
                if not active:
                    continue
                selected = [
                    span
                    for _, _, record in active
                    for span in record["spans"]
                    if span["label"] == entity
                ]
                self.reporter.start_batch(
                    model["model_id"], batch_index, len(active), stage="PENDING"
                )
                errors = []
                self.normalizer.normalize(
                    selected,
                    self.job_payload["language"],
                    lambda model, exc, stage: errors.append(
                        self.failed(model, exc, stage, len(active))
                    ),
                )
                for row, raw, record in active:
                    record["models"].extend(errors)
                    # Record successful no-op categories as well, so restart is deterministic.
                    outcome = errors[0] if errors else {"model_id": model["model_id"]}
                    record["state"]["normalizers"][entity] = outcome
                    if not errors:
                        record["models"].append(outcome)
                    self.save(row, raw, record)
                    if entity_index == len(ordered) - 1:
                        self.finalize(row, raw, record)
                if not errors:
                    self.reporter.complete_batch(model["model_id"], len(active))
        if not ordered:
            for row in self.rows:
                raw, record = self.load(row)
                self.finalize(row, raw, record)

    def run(self, models, payload):
        self.job_payload = payload
        self.ner(models)
        self.normalize()
        # An interrupted final commit may leave a fully checkpointed preview.
        for row in self.rows:
            raw, record = self.load(row)
            if not record.get("complete", False):
                self.finalize(row, raw, record)
