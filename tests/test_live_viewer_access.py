"""HTML viewer entrypoints must allow real unfinished pasted-text projects."""

import pytest

from app.main import create_app
from app.services.pipeline import process_job
from tests.auth_helpers import AccountClient
from tests.test_incremental import Predictor, controlled_stats


@pytest.mark.parametrize("prefix", ["", "/ner"])
def test_pasted_text_html_viewer_opens_after_disease_before_symptom(settings, prefix):
    settings = settings.model_copy(
        update={"app_prefix": prefix, "public_base_url": "http://testserver" + prefix}
    )
    app = create_app(settings)
    for identity in ("es-disease", "es-symptom"):
        app.state.registry.models[identity]["available"] = True
    with AccountClient(app) as client:
        response = client.post(
            prefix + "/api/jobs",
            data={
                "language": "es",
                "entities": ["DISEASE", "SYMPTOM"],
                "input_mode": "PASTED_TEXT",
                "pasted_text": "abc",
                "document_name": "clinical-note.txt",
            },
        )
        assert response.status_code == 202, response.text
        identity = response.json()["job_id"]
        for path in ("/jobs/", "/api/jobs/"):
            queued = client.get(prefix + path + identity + "/viewer")
            assert queued.status_code == 200 and queued.headers["content-type"].startswith(
                "text/html"
            )
        observations = []

        def observe(model, documents):
            if model["model_id"] != "es-symptom":
                return
            base = prefix + "/api/jobs/" + identity
            progress = client.get(base + "/progress").json()
            document = client.get(base + "/documents").json()["items"][0]
            annotations = client.get(
                base + "/documents/" + document["document_id"] + "/annotations"
            ).json()["items"]
            pages = [
                client.get(prefix + path)
                for path in (
                    "/jobs/" + identity + "/viewer",
                    "/api/jobs/" + identity + "/viewer",
                )
            ]
            dashboard = client.get(prefix + "/?lang=en")
            observations.append((progress, annotations, pages, dashboard.text))

        job = app.state.db.claim()
        process_job(
            job, settings, Predictor(observe), controlled_stats, lambda _: app.state.registry
        )
        assert len(observations) == 1
        progress, annotations, pages, dashboard = observations[0]
        assert progress["annotated_documents"] == 0 and progress["partial_results"]
        assert {row["label"] for row in annotations} == {"DISEASE"}
        for page in pages:
            assert page.status_code == 200, page.text
            assert page.headers["content-type"].startswith("text/html")
            assert 'id="annotated-text"' in page.text
        assert prefix + "/jobs/" + identity + "/viewer?lang=en" in dashboard
