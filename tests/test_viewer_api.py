import json
import time

from fastapi.testclient import TestClient

from app.services.cleanup import cleanup
from tests.viewer_fixtures import TEXT, seed_viewer


def test_document_contracts_pagination_and_unicode(settings):
    app, accepted, docs, spans = seed_viewer(settings)
    with TestClient(app) as client:
        base = "/api/jobs/" + accepted["token"]
        page = client.get(base + "/documents?limit=1").json()
        assert page["total"] == 2 and len(page["items"]) == 1 and "text" not in page["items"][0]
        identity = page["items"][0]["document_id"]
        assert client.get(base + "/documents?q=nested").json()["total"] == 1
        assert client.get(base + "/documents?has_annotations=false").json()["total"] == 1
        assert client.get(base + "/documents?label=DISEASE").json()["total"] == 1
        text = client.get(base + "/documents/" + identity + "?start=0&limit=1").json()
        assert text["text"] == "😀" and text["end"] == 1
        full = client.get(base + "/documents/" + identity).json()
        assert full["text"] == TEXT
        annotations = client.get(base + "/documents/" + identity + "/annotations?limit=2").json()
        assert annotations["total"] == 7 and len(annotations["items"]) == 2
        for row in client.get(base + "/documents/" + identity + "/annotations").json()["items"]:
            assert TEXT[row["start"] : row["end"]] == row["text"]
        assert client.get(base + "/documents/" + identity + "/statistics").status_code == 200
        assert client.get(base + "/viewer").status_code == 200
        assert client.get(base + "/documents/" + identity).headers["cache-control"] == "no-store"
        assert client.get(base + "/documents/" + "0" * 32).status_code == 404
        assert client.get("/api/jobs/" + "x" * 43 + "/documents/" + identity).status_code == 404
        assert client.get(base + "/documents?limit=101").status_code == 422
        # No other document is fetched or exposed by the text endpoint.
        assert "No mentions" not in json.dumps(full)


def test_72_hour_retention_every_private_route(settings, monkeypatch):
    app, accepted, _, _ = seed_viewer(settings)
    db = app.state.db
    job = db.get(accepted["token"])
    assert job["expires_at"] - job["completed_at"] == 72 * 3600
    root = app.state.jobs.storage.job(job["id"])
    with TestClient(app) as client:
        base = "/api/jobs/" + accepted["token"]
        identity = client.get(base + "/documents").json()["items"][0]["document_id"]
        routes = [
            "",
            "/viewer",
            "/documents",
            "/documents/" + identity,
            "/documents/" + identity + "/annotations",
            "/documents/" + identity + "/statistics",
            "/documents/" + identity + "/search?q=Severe",
            "/statistics",
            "/download/brat",
            "/download/tsv",
        ]
        monkeypatch.setattr("time.time", lambda: job["completed_at"] + 71 * 3600)
        for route in routes:
            assert client.get(base + route).status_code == 200
        monkeypatch.setattr("time.time", lambda: job["completed_at"] + 72 * 3600)
        for route in routes:
            assert client.get(base + route).status_code == 410
        cleanup(db, app.state.jobs.storage)
        cleanup(db, app.state.jobs.storage)
        assert not root.exists()
        assert db.get(accepted["token"])["payload"] == "{}"


def test_legacy_completed_job_backfills_private_viewer(settings):
    import shutil

    app, accepted, _, _ = seed_viewer(settings)
    root = app.state.jobs.storage.job(accepted["job_id"])
    shutil.rmtree(root / "viewer")
    with app.state.db.connect() as c:
        c.execute("DELETE FROM documents WHERE job_id=?", (accepted["job_id"],))
    with TestClient(app) as client:
        response = client.get("/api/jobs/" + accepted["token"] + "/documents")
        assert response.status_code == 200 and response.json()["total"] == 2
        assert (root / "viewer" / "index.json").exists()


def test_prefix_routes_origin_and_links(settings):
    settings = settings.model_copy(
        update={"app_prefix": "/ner", "public_base_url": "https://temu.bsc.es/ner"}
    )
    from app.main import create_app
    from tests.conftest import request_data

    with TestClient(create_app(settings)) as client:
        client.app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
        assert client.get("/ner/").status_code == 200
        assert "/ner/static/form.js" in client.get("/ner/").text
        assert client.get("/ner/health").status_code == 200
        docs = client.get("/ner/docs")
        assert docs.status_code == 200
        assert "cdn.jsdelivr.net" not in docs.text and "unpkg.com" not in docs.text
        assert "/ner/openapi.json" in docs.text
        assert "/ner/api/jobs" in client.get("/ner/openapi.json").json()["paths"]
        response = client.post(
            "/ner/api/jobs",
            data=request_data(),
            files={"files": ("x.txt", b"text")},
            headers={"Origin": "https://temu.bsc.es"},
        )
        assert response.status_code == 202
        assert response.json()["url"].startswith("https://temu.bsc.es/ner/jobs/")
        assert (
            client.post("/ner/api/jobs", headers={"Content-Length": str(100 * 1024**2)}).status_code
            == 413
        )
        assert (
            client.post("/ner/api/jobs", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )


def test_queued_jobs_do_not_spend_their_retention(settings, monkeypatch):
    from app.db import Database
    from tests.conftest import enqueue

    now = time.time()
    db = Database(settings)
    token = enqueue(db)
    assert db.get(token)["expires_at"] is None
    monkeypatch.setattr("time.time", lambda: now + 7 * 24 * 3600)
    db.claim()
    db.finish("job1", {"documents": 1})
    row = db.get(token)
    assert row["expires_at"] == row["completed_at"] + 72 * 3600


def test_retention_migration_never_revives_expired_jobs(settings):
    from app.db import Database
    from scripts.migrate_retention import migrate
    from tests.conftest import enqueue

    db = Database(settings)
    first = enqueue(db)
    db.claim()
    db.finish("job1")
    with db.connect() as c:
        c.execute("UPDATE jobs SET expires_at=completed_at+86400")
    assert migrate(db) == 1
    assert db.get(first)["expires_at"] - db.get(first)["completed_at"] == 72 * 3600
    with db.connect() as c:
        c.execute("UPDATE jobs SET expires_at=?", (time.time() - 1,))
    assert migrate(db) == 0


def test_thousand_document_index_and_cross_fragment_spans(settings):
    from app.api.schemas import Submission
    from app.main import create_app
    from app.visualization.repository import write_index

    app = create_app(settings)
    service = app.state.jobs
    service.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
    form = Submission(
        submitter_name="Test",
        submitter_email="large@example.org",
        language="es",
        entities=["DISEASE"],
    )
    text = "😀" + ("a" * 11999)
    documents = {f"doc-{i:04}.txt": text.encode() if i == 0 else b"x" for i in range(1000)}
    accepted = service.submit(form, list(documents.items()), "test-ip")
    job = service.db.claim()
    span = {
        "filename": "doc-0000.txt",
        "label": "DISEASE",
        "start_span": 4998,
        "end_span": 5005,
        "text": text[4998:5005],
        "score": None,
        "model_id": "test",
    }
    write_index(service.storage.job(job["id"]) / "viewer", documents, [span], [])
    from app.persistence.progress import ProgressRepository

    for record in json.loads(
        (service.storage.job(job["id"]) / "viewer" / "index.json").read_text()
    ):
        ProgressRepository(service.db).publish(
            job["id"],
            record["document_id"],
            record["annotation_count"],
            record["entities_by_label"],
            record["statistics"],
        )
    service.db.finish(job["id"], {"documents": 1000})
    with TestClient(app) as client:
        base = "/api/jobs/" + accepted["token"] + "/documents"
        page = client.get(base + "?limit=1").json()
        assert page["total"] == 1000 and len(page["items"]) == 1
        assert len(json.dumps(page)) < 1000
        identity = page["items"][0]["document_id"]
        first = client.get(base + "/" + identity + "?limit=5000").json()
        second = client.get(base + "/" + identity + "?start=5000&limit=5000").json()
        assert first["total_characters"] == 12000 and len(first["text"]) == 5000
        assert second["start"] == 5000 and second["text"] == text[5000:10000]
        for start, end in [(0, 5000), (5000, 10000)]:
            rows = client.get(
                base + "/" + identity + f"/annotations?start={start}&end={end}"
            ).json()["items"]
            assert rows[0]["start"] == 4998 and rows[0]["end"] == 5005
            assert rows[0]["text"] == text[4998:5005]


def test_global_search_wraps_without_losing_unicode_offsets(settings):
    app, accepted, _, _ = seed_viewer(settings)
    with TestClient(app) as client:
        base = "/api/jobs/" + accepted["token"] + "/documents"
        identity = client.get(base).json()["items"][0]["document_id"]
        result = client.get(
            base + "/" + identity + "/search", params={"q": "😀", "start": 40}
        ).json()
        assert result == {"start": 0, "end": 1, "total": 1, "wrapped": True}
        assert client.get(base + "/" + identity + "/search?q=absent").json()["start"] is None
