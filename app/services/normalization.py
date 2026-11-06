"""ner_lab bi-encoder/FlatIP normalization and a private three-language idle-TTL cache."""

import fcntl
import hashlib
import json
import logging
import math
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path

from app.services.model_cache import ModelCache
from app.services.normalization_catalog import CATEGORIES, NormalizationCatalog, file_sha256


class NormalizationUnavailable(ValueError):
    pass


class NormalizationCache:
    def __init__(self, settings):
        self.s = settings
        self.root = settings.normalization_cache

    @contextmanager
    def locked(self, blocking=True):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".cache.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            yield True

    def prune(self, keep=None):
        now = time.time()
        directories = [
            path
            for path in self.root.iterdir()
            if path.is_dir() and re.fullmatch(r"[a-z]{2}", path.name)
        ]
        for path in directories:
            if now - path.stat().st_mtime >= self.s.normalization_cache_ttl_hours * 3600:
                shutil.rmtree(path)
        directories = sorted(
            [path for path in directories if path.exists() and path.name != keep],
            key=lambda path: path.stat().st_mtime,
        )
        allowed = self.s.normalization_cache_languages - int(keep is not None)
        for path in directories[: max(0, len(directories) - allowed)]:
            shutil.rmtree(path)

    def sweep(self):
        if self.root.exists():
            with self.locked(blocking=False) as acquired:
                if acquired:
                    self.prune()

    def load_or_build(self, resource, model, retriever):
        import faiss
        import pandas as pd

        language, entity = resource["resolved_language"], resource["entity"]
        signature = {
            "gazetteer_sha256": resource["sha256"],
            "repository": model.get("repository"),
            "revision": model.get("resolved_revision") or model.get("version"),
            "pooling": model["pooling"],
            "batch_size": self.s.normalization_batch_size,
            "max_length": 256,
            "index": "FlatIP",
            "runtime": {
                name: version(name) for name in ("torch", "transformers", "faiss-cpu", "lab")
            },
        }
        if not model.get("resolved_revision"):
            weights = sorted(path for path in Path(model["model_dir"]).rglob("*") if path.is_file())
            signature["revision"] = hashlib.sha256(
                "".join(file_sha256(path) for path in weights).encode()
            ).hexdigest()
        with self.locked():
            self.prune(keep=language)
            parent = self.root / language
            parent.mkdir(exist_ok=True)
            for orphan in parent.glob(".building-*"):
                shutil.rmtree(orphan)
            destination = parent / entity
            manifest = destination / "manifest.json"
            stored = json.loads(manifest.read_text()) if manifest.is_file() else {}
            hit = stored.get("signature") == signature
            if hit:
                if file_sha256(destination / "index.faiss") != stored.get(
                    "index_sha256"
                ) or file_sha256(destination / "vocabulary.parquet") != stored.get(
                    "vocabulary_sha256"
                ):
                    raise NormalizationUnavailable(
                        "Cached terminology files failed integrity validation"
                    )
                vocabulary = pd.read_parquet(destination / "vocabulary.parquet")
                index = faiss.read_index(str(destination / "index.faiss"))
                if index.ntotal != len(vocabulary) or index.d != stored["dimensions"]:
                    raise NormalizationUnavailable("Cached terminology index is inconsistent")
                if not isinstance(index, faiss.IndexIDMap2) or not isinstance(
                    faiss.downcast_index(index.index), faiss.IndexFlatIP
                ):
                    raise NormalizationUnavailable("Cached terminology index must be exact FlatIP")
                retriever.set_vocab(vocabulary)
                retriever.faiss_index = index
            else:
                if file_sha256(resource["file"]) != resource["sha256"]:
                    raise NormalizationUnavailable("Terminology changed since admission")
                from lab.nel.retrieval import build_vocabulary

                vocabulary = build_vocabulary(pd.read_parquet(resource["file"]))
                estimate = (
                    len(vocabulary) * getattr(retriever.model.config, "hidden_size", 1024) * 4
                    + resource["file"].stat().st_size
                )
                if shutil.disk_usage(parent).free < estimate + self.s.min_free_disk_mb * 1024**2:
                    raise NormalizationUnavailable("Insufficient space for terminology index")
                temporary = parent / (".building-" + uuid.uuid4().hex)
                temporary.mkdir()
                try:
                    retriever.fit_faiss(
                        vocab=vocabulary, batch_size=self.s.normalization_batch_size
                    )
                    faiss.write_index(retriever.faiss_index, str(temporary / "index.faiss"))
                    vocabulary.to_parquet(temporary / "vocabulary.parquet", index=False)
                    (temporary / "manifest.json").write_text(
                        json.dumps(
                            {
                                "signature": signature,
                                "dimensions": retriever.faiss_index.d,
                                "terms": len(vocabulary),
                                "built_at": time.time(),
                                "index_sha256": file_sha256(temporary / "index.faiss"),
                                "vocabulary_sha256": file_sha256(temporary / "vocabulary.parquet"),
                            },
                            indent=2,
                        )
                    )
                    if destination.exists():
                        shutil.rmtree(destination)
                    temporary.rename(destination)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            # Touch only a language directory. No mention/query/document is cached here.
            import os

            os.utime(parent, None)
        return {"cache_hit": hit, "signature": signature}


class NormalizationSession:
    def __init__(self, settings, job_root, catalog=None):
        self.s = settings
        self.catalog = catalog or NormalizationCatalog(settings)
        self.models = ModelCache(settings, job_root)
        self.cache = NormalizationCache(settings)
        self.encoder = None
        self.encoder_key = None
        self.prepared = {}
        self.metadata = []

    def _encoder(self, resource):
        from lab.nel.retrieval import TransformerFaissRetriever

        language = resource["resolved_language"]
        if language not in self.prepared:
            failure = None
            for index, candidate in enumerate(resource["models"]):
                try:
                    model = self.models.prepare(
                        {**candidate, "model_id": f"normalizer-{language}-{index}"}
                    )
                    # A local snapshot path prevents remote code/model-name dispatch.
                    encoder = TransformerFaissRetriever(
                        str(model["model_dir"]),
                        f_type="FlatIP",
                        max_length=256,
                        batch_size=self.s.normalization_batch_size,
                        device=self.s.device,
                        use_gpu=False,
                        pooling=model.get("pooling", "cls"),
                    )
                    self.prepared[language] = model
                    self.encoder_key = language
                    self.encoder = encoder
                    break
                except Exception as exc:
                    failure = exc
                    logging.getLogger("temu.normalization").warning(
                        "encoder_unavailable language=%s repository=%s error_type=%s",
                        language,
                        candidate.get("repository") or "local",
                        type(exc).__name__,
                    )
            if language not in self.prepared:
                raise NormalizationUnavailable(
                    "No configured terminology encoder could be loaded"
                ) from failure
        model = self.prepared[language]
        if self.encoder_key != language:
            self.encoder = None
            self.encoder = TransformerFaissRetriever(
                str(model["model_dir"]),
                f_type="FlatIP",
                max_length=256,
                batch_size=self.s.normalization_batch_size,
                device=self.s.device,
                use_gpu=False,
                pooling=model.get("pooling", "cls"),
            )
            self.encoder_key = language
        return model, self.encoder

    def normalize(self, spans, language, on_error):
        for entity in CATEGORIES:
            selected = [row for row in spans if row["label"] == entity]
            if not selected:
                continue
            try:
                resource = self.catalog.resolve(language, entity)
                if resource is None:
                    raise NormalizationUnavailable("No terminology resource for category")
                model, encoder = self._encoder(resource)
                cached = self.cache.load_or_build(resource, model, encoder)
                mentions = list(dict.fromkeys(row["text"] for row in selected))
                terms, codes, scores = encoder.get_candidates(
                    mentions,
                    k=self.s.normalization_top_k,
                    batch_size=self.s.normalization_batch_size,
                )
                lookup = {}
                for text, row_terms, row_codes, row_scores in zip(
                    mentions, terms, codes, scores, strict=True
                ):
                    candidates = [
                        {"code": str(code), "term": str(term), "score": float(score)}
                        for term, code, score in zip(row_terms, row_codes, row_scores, strict=True)
                    ]
                    if not candidates or any(
                        not math.isfinite(item["score"]) for item in candidates
                    ):
                        raise NormalizationUnavailable("Invalid terminology candidates")
                    lookup[text] = {
                        **candidates[0],
                        "candidates": candidates,
                        "language": resource["resolved_language"],
                        "requested_language": language,
                        "fallback_to_english": resource["fallback_to_english"],
                        "model": model.get("repository") or "local-encoder",
                        "model_revision": cached["signature"]["revision"],
                        "gazetteer_sha256": resource["sha256"],
                        "code_system": resource.get("code_system"),
                        "index": "FlatIP",
                        "max_length": 256,
                    }
                for row in selected:
                    row["normalization"] = lookup[row["text"]]
                self.metadata.append(
                    {
                        "entity": entity,
                        "language": resource["resolved_language"],
                        "model": model.get("repository"),
                        "revision": cached["signature"]["revision"],
                        "gazetteer_sha256": resource["sha256"],
                        "cache_hit": cached["cache_hit"],
                        "fallback_to_english": resource["fallback_to_english"],
                    }
                )
            except Exception as exc:
                on_error({"model_id": f"normalizer-{language}-{entity}"}, exc, "NORMALIZATION")
        return spans

    def close(self):
        self.encoder = None
