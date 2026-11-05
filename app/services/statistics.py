import json
import os
from collections import Counter
from importlib.metadata import version
from pathlib import Path


def statistics(documents: dict[str, str], spans: list[dict], language: str, tokenizer_path: str):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
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
            "words": "ner_lab words_of: UAX #29, containing a letter or digit",
            "tokens": "model subwords without special tokens",
            "offsets": "Unicode code points [start,end)",
        },
    }, rows
