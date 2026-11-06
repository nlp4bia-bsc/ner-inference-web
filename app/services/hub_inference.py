"""Hugging Face token classifiers with ner_lab's original-coordinate windows/decoder."""

from pathlib import Path
from time import monotonic

from app.services.inference import NerLabSession


class ModelSchemaError(ValueError):
    pass


def label_mapping(model, vocabulary):
    labels = set()
    for value in vocabulary.values():
        if value == "O":
            continue
        if not value.startswith(("B-", "I-")) or len(value) < 3:
            raise ModelSchemaError("Checkpoint does not declare BIO entity labels")
        labels.add(value[2:])
    if not labels or "O" not in vocabulary.values():
        raise ModelSchemaError("Checkpoint has no entity label schema")
    mapping = dict(model["label_mapping"])
    categories = set(mapping.values())
    for label in labels:
        if label not in mapping:
            if len(categories) != 1:
                raise ModelSchemaError("Checkpoint labels do not match configured categories")
            mapping[label] = next(iter(categories))
    return mapping


class HubSession(NerLabSession):
    def predict(self, model, documents, output, device):
        if (Path(model["model_dir"]) / "encoding.json").is_file():
            spans, meta = super().predict(model, documents, output, device)
            mapping = label_mapping(
                model, {i: label for label, i in meta["encoding"]["label2id"].items()}
            )
            return spans, {
                **meta,
                "label_mapping": mapping,
                "repository": model.get("repository"),
                "resolved_revision": model.get("resolved_revision"),
                "cache_hit": model.get("cache_hit"),
            }

        from lab.ner.encoding import Encoder, describe_encoder
        from lab.ner.inference.io import read_documents
        from lab.ner.inference.loading import resolve_device
        from lab.ner.inference.prediction import decode_spans, predict_logits
        from transformers import AutoConfig, AutoModelForTokenClassification, AutoTokenizer

        started = monotonic()
        key = (model["model_dir"], model.get("resolved_revision"), device)
        loaded = key not in self.cache
        if loaded:
            while len(self.cache) >= self.max_models:
                _, old = self.cache.popitem(last=False)
                del old
            config = AutoConfig.from_pretrained(
                model["model_dir"], local_files_only=True, trust_remote_code=False
            )  # nosec B615 -- resolved local snapshot
            if config.architectures and not any(
                "TokenClassification" in name for name in config.architectures
            ):
                raise ModelSchemaError("Checkpoint is not a token classifier")
            vocabulary = {int(i): label for i, label in config.id2label.items()}
            mapping = label_mapping(model, vocabulary)
            tokenizer = AutoTokenizer.from_pretrained(
                model["model_dir"], local_files_only=True, trust_remote_code=False, use_fast=True
            )  # nosec B615 -- local resolved snapshot
            if not tokenizer.is_fast:
                raise ModelSchemaError("Fast tokenizer required for original offsets")
            weights, loading = AutoModelForTokenClassification.from_pretrained(
                model["model_dir"],
                local_files_only=True,
                trust_remote_code=False,
                output_loading_info=True,
            )  # nosec B615 -- local resolved snapshot
            if loading.get("missing_keys") or loading.get("mismatched_keys"):
                raise ModelSchemaError("Checkpoint would initialize untrained weights")
            if set(vocabulary) != set(range(weights.config.num_labels)):
                raise ModelSchemaError("Invalid classifier label indexes")
            weights.to(resolve_device(device))
            weights.eval()
            maximum = min(
                512,
                tokenizer.model_max_length,
                getattr(weights.config, "max_position_embeddings", 512),
            )
            self.cache[key] = (
                weights,
                tokenizer,
                {"vocabulary": vocabulary, "label_mapping": mapping, "maximum": maximum},
            )
        self.cache.move_to_end(key)
        weights, tokenizer, description = self.cache[key]
        encoder = Encoder(
            tokenizer,
            next(label[2:] for label in description["vocabulary"].values() if label != "O"),
            model["language"],
            max_length=description["maximum"],
            min_sentence_tokens=1,
            require_target_label=False,
        )
        # Empty-gold inference windows use the actual classifier's O/tag indexes.
        encoder.id2label = description["vocabulary"]
        encoder.label2id = {label: i for i, label in encoder.id2label.items()}
        encoder.vocabulary = {
            **encoder.vocabulary,
            "id2label": encoder.id2label,
            "label2id": encoder.label2id,
        }
        rows = encoder.encode(read_documents(documents))
        if rows.empty:
            raise ModelSchemaError("No inference windows")
        logits = predict_logits(
            model=weights,
            tokenizer=tokenizer,
            rows=rows,
            batch_size=model.get("batch_size", 16),
            device=device,
            pad_to_multiple_of=8,
        )
        spans = decode_spans(
            rows=rows,
            predictions=logits,
            tokenizer=tokenizer,
            id2label=encoder.id2label,
            texts=documents,
            min_score=model.get("min_score", 0),
        )
        meta = {
            "model_id": model["model_id"],
            "version": model.get("version"),
            "repository": model.get("repository"),
            "resolved_revision": model.get("resolved_revision"),
            "cache_hit": model.get("cache_hit"),
            "checkpoint_loaded": loaded,
            "language": model["language"],
            "encoding": describe_encoder(encoder),
            "model": {"architecture": type(weights).__name__},
            "label_mapping": description["label_mapping"],
            "n_documents": len(documents),
            "n_windows": len(rows),
            "seconds": monotonic() - started,
            "device": device,
        }
        self.timings.append(meta)
        return spans.to_dict("records"), meta
