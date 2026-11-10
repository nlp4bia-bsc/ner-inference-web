import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path


def statistics(documents: dict[str, str], spans: list[dict], language: str, tokenizer_path: str):
    requested_language = language
    # Other is metadata, not an ISO code understood by ner_lab's segmenters.
    # Use a fixed fallback and record it rather than guessing from clinical text.
    language = "en" if language == "oth" else language
    from lab.core import (
        build_corpus,
        compute_annotation_stats,
        compute_text_stats,
        describe_sentence_segmenter,
        span_dataframe,
    )
    from lab.core.stats.annotations import AnnotationMeasurements
    from lab.core.stats.primitives import DEFAULT_MATTR_WINDOW, load_tokenizer
    from lab.core.stats.text import TextMeasurements

    frame = build_corpus(documents, span_dataframe(spans, scored=True), on_mismatch="documents")
    # Both public aggregators load a tokenizer once each, not once per document.
    text = json.loads(
        compute_text_stats(frame, tokenizer_path, language).to_json(orient="records")
    )[0]
    text["language"] = requested_language
    annotations = json.loads(
        compute_annotation_stats(frame, tokenizer_path).to_json(orient="records")
    )[0]
    tokenizer = load_tokenizer(tokenizer_path)
    rows = []
    for row in frame.itertuples(index=False):
        t, a = TextMeasurements(), AnnotationMeasurements()
        t.add(row.text, language, tokenizer, DEFAULT_MATTR_WINDOW)
        a.add(row.text, json.loads(row.entities_json), tokenizer)
        rows.append(
            {
                "filename": row.doc_id,
                "characters": len(row.text),
                "words": sum(t.word_counts),
                "tokens": sum(t.token_counts),
                "sentences": sum(t.sentence_counts),
                "entities_total": sum(a.mention_counts),
                "processing_status": "COMPLETED",
            }
        )
    summary = {
        "documents": len(documents),
        "annotations": len(spans),
        "characters": sum(map(len, documents.values())),
        "documents_with_entities": len({r["filename"] for r in spans}),
        "mentions_by_label": dict(Counter(r["label"] for r in spans)),
        "words": text["words"],
        "tokens": text["tokens"],
        "sentences": text["sentences"],
    }
    # Public tokenizer reference is a stable local directory basename, not its private path.
    return {
        "ner_lab": {"text": text, "annotations": annotations},
        "operational": summary,
        "definitions": {
            "tokenizer": Path(tokenizer_path).name,
            "transformers_version": version("transformers"),
            "tokenizers_version": version("tokenizers"),
            "segmenter": describe_sentence_segmenter(language),
            "sentence_language": language,
            "words": "ner_lab words_of: UAX #29, containing a letter or digit",
            "tokens": "model subwords without special tokens",
            "offsets": "Unicode code points [start,end)",
        },
    }, rows


class StreamingStatistics:
    """Native measurements and one reference tokenizer, accumulated without a corpus mapping."""

    def __init__(self, language, tokenizer_path):
        from lab.core.stats.annotations import AnnotationMeasurements
        from lab.core.stats.primitives import load_tokenizer
        from lab.core.stats.text import TextMeasurements

        self.document_language = language
        self.language = "en" if language == "oth" else language
        self.reference = tokenizer_path
        self.tokenizer = load_tokenizer(tokenizer_path)
        self.text = TextMeasurements()
        self.annotations = AnnotationMeasurements()
        self.characters = 0

    def add(self, filename, text, spans):
        from lab.core.stats.primitives import DEFAULT_MATTR_WINDOW

        entities = [
            {"start": r["start_span"], "end": r["end_span"], "label": r["label"], "text": r["text"]}
            for r in spans
        ]
        self.text.add(text, self.language, self.tokenizer, DEFAULT_MATTR_WINDOW)
        self.annotations.add(text, entities, self.tokenizer)
        self.characters += len(text)
        return {
            "filename": filename,
            "characters": len(text),
            "words": self.text.word_counts[-1],
            "tokens": self.text.token_counts[-1],
            "sentences": self.text.sentence_counts[-1],
            "entities_total": len(spans),
            "processing_status": "COMPLETED",
        }

    def result(self):
        import pandas as pd
        from lab.core import describe_sentence_segmenter
        from lab.core.stats.primitives import share

        a = self.annotations.row()
        for label, count in self.annotations.labels.most_common():
            a["mentions_" + label] = count
            a["pct_" + label] = share(count, a["mentions"])

        def native(value):
            return json.loads(pd.DataFrame([value]).to_json(orient="records"))[0]

        t = native(self.text.row(self.language))
        t["language"] = self.document_language
        return {
            "ner_lab": {"text": t, "annotations": native(a)},
            "operational": {
                "documents": self.annotations.documents,
                "annotations": sum(self.annotations.mention_counts),
                "documents_with_entities": self.annotations.annotated_documents,
                "characters": self.characters,
                "words": t["words"],
                "tokens": t["tokens"],
                "sentences": t["sentences"],
                "mentions_by_label": dict(self.annotations.labels),
            },
            "definitions": {
                "tokenizer": Path(self.reference).name,
                "segmenter": describe_sentence_segmenter(self.language),
                "sentence_language": self.language,
                "transformers_version": version("transformers"),
                "tokens": "reference tokenizer subwords without special tokens",
                "words": "ner_lab Unicode words_of",
                "offsets": "Unicode code points [start,end)",
            },
        }
