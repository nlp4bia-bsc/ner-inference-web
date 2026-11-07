"""Parquet lexical normalization and opt-in ner_lab/FlatIP with a private idle-TTL cache."""

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

from app.domain.normalization_references import merge_reference_values
from app.persistence.job_locks import JobContentChanged
from app.services.model_cache import ModelCache
from app.services.normalization_catalog import CATEGORIES, NormalizationCatalog, file_sha256


class NormalizationUnavailable(ValueError):
    def __init__(self, message, reason_code="NORMALIZATION_UNAVAILABLE"):
        super().__init__(message)
        self.reason_code = reason_code


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

    def load_or_build(self, resource, model, retriever, on_progress=None):
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
        if on_progress:
            on_progress("WAITING_FOR_INDEX")
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
                if on_progress:
                    on_progress("LOADING_INDEX")
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

                if on_progress:
                    on_progress("READING_TERMINOLOGY")
                dictionary = pd.read_parquet(resource["file"])
                vocabulary = build_vocabulary(dictionary)
                if "references" in dictionary.columns:
                    references = dictionary.groupby("code", sort=False)["references"].agg(
                        merge_reference_values
                    )
                    vocabulary["references"] = vocabulary["code"].map(references).fillna("[]")
                del dictionary
                estimate = (
                    len(vocabulary) * getattr(retriever.model.config, "hidden_size", 1024) * 4
                    + resource["file"].stat().st_size
                )
                if shutil.disk_usage(parent).free < estimate + self.s.min_free_disk_mb * 1024**2:
                    raise NormalizationUnavailable("Insufficient space for terminology index")
                temporary = parent / (".building-" + uuid.uuid4().hex)
                temporary.mkdir()
                try:
                    from app.services.inference_progress import encoder_progress

                    with encoder_progress(
                        retriever.model, on_progress, "BUILDING_INDEX", len(vocabulary), "pairs"
                    ):
                        retriever.fit_faiss(
                            vocab=vocabulary, batch_size=self.s.normalization_batch_size
                        )
                    if on_progress:
                        on_progress("SAVING_INDEX")
                    faiss.write_index(retriever.faiss_index, str(temporary / "index.faiss"))
                    vocabulary.to_parquet(temporary / "vocabulary.parquet", index=False)
                    (temporary / "manifest.json").write_text(
                        json.dumps(
                            {
                                "signature": signature,
                                "dimensions": retriever.faiss_index.d,
                                "terms": len(vocabulary),
                                "normalized_forms": int(vocabulary["term"].nunique()),
                                "concepts": int(vocabulary["code"].nunique()),
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
        return {
            "cache_hit": hit,
            "signature": signature,
            "pairs": len(vocabulary),
            "normalized_forms": stored.get("normalized_forms")
            if hit and "normalized_forms" in stored
            else int(vocabulary["term"].nunique()),
            "concepts": stored.get("concepts")
            if hit and "concepts" in stored
            else int(vocabulary["code"].nunique()),
            "references": dict(zip(vocabulary["code"], vocabulary["references"], strict=True))
            if "references" in vocabulary.columns
            else {},
        }


class NormalizationSession:
    def __init__(self, settings, job_root, catalog=None, *, method="levenshtein", threshold=0.8):
        self.s = settings
        self.catalog = catalog or NormalizationCatalog(settings)
        if (
            method not in ("exact", "levenshtein", "bi_encoder")
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("Invalid normalization method or threshold")
        self.method, self.threshold, self.job_root = method, threshold, job_root
        self.models = None
        self.lexical = {}
        self.last_completed_entities = set()
        self.loaded_index = None
        self.loaded_metadata = None
        self.cache = NormalizationCache(settings)
        self.encoder = None
        self.encoder_key = None
        self.prepared = {}
        self.metadata = []
        self.on_progress = None
        self.current_entity = None

    def report(self, stage, completed=0, total=None, unit=None):
        if self.on_progress:
            self.on_progress(self.current_entity, stage, completed, total, unit)

    def _encoder(self, resource):
        from lab.nel.retrieval import TransformerFaissRetriever

        language = resource["resolved_language"]
        if self.models is None:
            self.models = ModelCache(self.s, self.job_root)
        if language not in self.prepared:
            failure = None
            for index, candidate in enumerate(resource["models"]):
                try:
                    self.models.on_progress = self.report
                    model = self.models.prepare(
                        {**candidate, "model_id": f"normalizer-{language}-{index}"}
                    )
                    # A local snapshot path prevents remote code/model-name dispatch.
                    self.report("LOADING_MODEL")
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
                except JobContentChanged:
                    raise
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
            self.report("LOADING_MODEL")
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

    @staticmethod
    def candidate(term, code, score, resource, references="[]"):
        primary = {"code_system": resource.get("code_system") or "Terminology", "code": str(code)}
        return {
            "term": str(term),
            "code": str(code),
            "score": float(score),
            "code_system": resource.get("code_system"),
            "references": [primary, *[row for row in json.loads(references) if row != primary]],
        }

    def retrieve(self, resource, mentions):
        if self.method != "bi_encoder":
            from app.services.lexical_normalization import LexicalMatcher

            key = (resource["resolved_language"], resource["entity"], resource["sha256"])
            hit = key in self.lexical
            if not hit:
                self.lexical[key] = LexicalMatcher(resource, self.report)
            matcher = self.lexical[key]
            rows = matcher.match(
                mentions, self.method, self.threshold, self.s.normalization_top_k, self.report
            )
            results = [
                [
                    self.candidate(
                        row["term"], row["code"], row["score"], resource, row["references"]
                    )
                    for row in candidates
                ]
                for candidates in rows
            ]
            return results, {
                "model": None,
                "revision": None,
                "index": "Parquet-sorted-keys",
                "max_length": None,
                **matcher.metadata,
                "cache_hit": hit or matcher.metadata["cache_hit"],
            }
        from app.services.inference_progress import encoder_progress

        model, encoder = self._encoder(resource)
        key = (resource["resolved_language"], resource["entity"], resource["sha256"], id(encoder))
        if key != self.loaded_index:
            self.loaded_metadata = self.cache.load_or_build(
                resource, model, encoder, on_progress=self.report
            )
            self.loaded_index = key
            cached = self.loaded_metadata
        else:
            self.report("LOADING_INDEX")
            cached = {**self.loaded_metadata, "cache_hit": True}
        with encoder_progress(encoder.model, self.report, "NORMALIZING", len(mentions), "mentions"):
            terms, codes, scores = encoder.get_candidates(
                mentions, k=self.s.normalization_top_k, batch_size=self.s.normalization_batch_size
            )
        results = [
            [
                self.candidate(
                    term, code, score, resource, cached["references"].get(str(code), "[]")
                )
                for term, code, score in zip(row_terms, row_codes, row_scores, strict=True)
            ]
            for row_terms, row_codes, row_scores in zip(terms, codes, scores, strict=True)
        ]
        if any(
            not candidates or any(not math.isfinite(row["score"]) for row in candidates)
            for candidates in results
        ):
            raise NormalizationUnavailable("Invalid terminology candidates")
        return results, {
            "model": model.get("repository") or "local-encoder",
            "revision": cached["signature"]["revision"],
            "index": "FlatIP",
            "max_length": 256,
            "cache_hit": cached["cache_hit"],
            **{key: cached[key] for key in ("pairs", "normalized_forms", "concepts")},
        }

    def normalize(self, spans, language, on_error):
        self.last_completed_entities = set()
        for entity in CATEGORIES:
            selected = [row for row in spans if row["label"] == entity]
            if not selected:
                continue
            self.current_entity = entity
            for row in selected:
                row.pop("normalization", None)
            try:
                resource = self.catalog.resolve(language, entity, self.method)
                if resource is None:
                    raise NormalizationUnavailable(
                        "No terminology resource for category",
                        self.catalog.unavailability_reason(language, entity, self.method),
                    )
                mentions = list(dict.fromkeys(row["text"] for row in selected))
                predictions, details = self.retrieve(resource, mentions)
                lookup = {}
                for text, candidates in zip(mentions, predictions, strict=True):
                    if not candidates:
                        continue  # A lexical miss is a valid outcome, not a model failure.
                    lookup[text] = {
                        **candidates[0],
                        "candidates": candidates,
                        "method": self.method,
                        "threshold": self.threshold if self.method == "levenshtein" else None,
                        "score_kind": "cosine_similarity"
                        if self.method == "bi_encoder"
                        else "normalized_levenshtein"
                        if self.method == "levenshtein"
                        else "exact_match",
                        "language": resource["resolved_language"],
                        "requested_language": language,
                        "fallback_to_english": resource["fallback_to_english"],
                        "model": details["model"],
                        "model_revision": details["revision"],
                        "gazetteer_sha256": resource["sha256"],
                        "code_system": resource.get("code_system"),
                        "index": details["index"],
                        "max_length": details["max_length"],
                    }
                for row in selected:
                    if row["text"] in lookup:
                        row["normalization"] = lookup[row["text"]]
                self.metadata.append(
                    {
                        "entity": entity,
                        "language": resource["resolved_language"],
                        "method": self.method,
                        "threshold": self.threshold if self.method == "levenshtein" else None,
                        "fallback_to_english": resource["fallback_to_english"],
                        "gazetteer_sha256": resource["sha256"],
                        "mentions": len(mentions),
                        "matched": len(lookup),
                        "unmatched": len(mentions) - len(lookup),
                        **details,
                    }
                )
                self.last_completed_entities.add(entity)
            except JobContentChanged:
                raise
            except Exception as exc:
                on_error({"model_id": f"normalizer-{language}-{entity}"}, exc, "NORMALIZATION")
        return spans

    def close(self):
        self.encoder = None
        self.loaded_index = self.loaded_metadata = None
        for matcher in self.lexical.values():
            matcher.close()
        self.lexical.clear()
