"""Small synthetic overlap corpus, not biomedical model predictions."""

from app.api.schemas import Submission
from app.services.export import package
from app.visualization.repository import write_index

TEXT = "😀 Severe chronic kidney disease\r\nA B C D E F\t漢字 e\u0301.\n<script>alert(1)</script>"


def seed_viewer(settings, text=TEXT, ranges=None):
    from app.main import create_app

    app = create_app(settings)
    service = app.state.jobs
    form = Submission(
        submitter_name="Synthetic fixture",
        submitter_email="fixture@example.org",
        language="es",
        entities=["DISEASE"],
    )
    # Admission uses the same code path; test-only model availability, never deployed config.
    service.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
    from tests.auth_helpers import acting_as

    with acting_as(app):
        accepted = service.submit(
            form,
            [("nested/sample.txt", text.encode()), ("empty-predictions.txt", b"No mentions here.")],
            "fixture-ip",
        )
    job = service.db.claim()
    docs = {"nested/sample.txt": text.encode(), "empty-predictions.txt": b"No mentions here."}
    if ranges is None:
        start = text.index("Severe")
        cross = text.index("A B C")
        ranges = [
            ("SEVERITY", start, text.index("\r")),
            ("DISEASE", text.index("chronic"), text.index("\r")),
            ("FINDING", text.index("chronic"), text.index("\r")),
            ("CROSS_A", cross, cross + 5),
            ("CROSS_B", cross + 4, cross + 9),
            ("EMOJI", 0, 1),
            ("THIRD", text.index("kidney"), text.index("\r")),
        ]
    spans = [
        {
            "filename": "nested/sample.txt",
            "label": label,
            "start_span": a,
            "end_span": b,
            "text": text[a:b],
            "score": 0.85,
            "model_id": "synthetic-test-only",
        }
        for label, a, b in ranges
    ]
    root = service.storage.job(job["id"])
    per_doc = [
        {
            "filename": name,
            "characters": len(raw.decode()),
            "words": None,
            "tokens": None,
            "sentences": None,
            "entities_total": len(ranges) if name.startswith("nested") else 0,
            "processing_status": "COMPLETED",
        }
        for name, raw in docs.items()
    ]
    stats = {
        "operational": {
            "documents": 2,
            "annotations": len(ranges),
            "characters": len(text) + 17,
            "words": None,
            "tokens": None,
            "sentences": None,
            "seconds": 0.1,
        }
    }
    package(
        root / "output",
        docs,
        spans,
        {**form.model_dump(), "entities": [r[0] for r in ranges]},
        stats,
        per_doc,
        {"source": "synthetic overlap fixture"},
    )
    write_index(root / "viewer", docs, spans, per_doc)
    import json

    from app.persistence.progress import ProgressRepository

    for row in json.loads((root / "viewer" / "index.json").read_text()):
        ProgressRepository(service.db).publish(
            job["id"],
            row["document_id"],
            row["annotation_count"],
            row["entities_by_label"],
            row["statistics"],
        )
    service.db.finish(job["id"], stats["operational"])
    return app, accepted, docs, spans
