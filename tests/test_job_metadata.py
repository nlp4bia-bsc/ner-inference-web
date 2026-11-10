"""Real admission, routing and history for named jobs and unspecified languages."""

import io
import json
import zipfile

import pytest
from pydantic import ValidationError

from app.api.schemas import Submission
from app.errors import ServiceError
from app.services.pipeline import process_job
from tests.conftest import request_data
from tests.test_incremental import Predictor, controlled_stats

MULTILINGUAL = "DT4H_XLM-R_mtl_multilingual_multilabel"


@pytest.mark.parametrize("mode", ["txt", "zip", "paste", "custom"])
def test_job_name_admission_and_history(client, mode):
    fields = request_data()
    if mode == "paste":
        fields.update(input_mode="PASTED_TEXT", pasted_text="Cancer.", document_name="report.txt")
        response = client.post("/api/jobs", data=fields)
        expected = "report"
    else:
        content = b"Cancer."
        name = "clinical.note.txt"
        if mode == "zip":
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                archive.writestr("nested/report.txt", content)
            name, content = "clinical.batch.zip", stream.getvalue()
        if mode == "custom":
            fields["job_name"] = "  My clinical project  "
        response = client.post("/api/jobs", data=fields, files={"files": (name, content)})
        expected = "My clinical project" if mode == "custom" else name.rsplit(".", 1)[0]
    assert response.status_code == 202, response.text
    accepted = response.json()
    status = client.get("/api/jobs/" + accepted["job_id"]).json()
    assert status["job_name"] == expected
    assert client.app.state.jobs.history()[0]["name"] == expected
    assert expected in client.get("/?lang=en").text
    # Older records continue to use their first document name without a migration.
    with client.app.state.db.connect() as connection:
        connection.execute("UPDATE jobs SET payload=json_remove(payload,'$.job_name')")
    assert client.app.state.jobs.history()[0]["name"].endswith(".txt")
    assert client.get("/api/jobs/" + accepted["job_id"]).json()["job_name"].endswith(".txt")


def test_other_language_routes_multilingual_job_and_keeps_oth_metadata(client, settings):
    registry = client.app.state.registry
    registry.models[MULTILINGUAL]["available"] = True
    options = client.get("/api/languages").json()
    assert {"code": "oth", "display_name": "Other"} in options
    rows = client.get("/api/models?language=oth").json()
    assert rows and all(row["language"] == "mul" for row in rows)
    assert all(row["allows_other"] for row in rows if row["model_id"])
    with pytest.raises(ServiceError):
        registry.select("oth", [], ["es-disease"])
    response = client.post(
        "/api/jobs",
        data={
            "language": "oth",
            "other_language": "  Turkish  ",
            "job_name": "Turkish clinical project",
            "models": [MULTILINGUAL],
            "input_mode": "PASTED_TEXT",
            "pasted_text": "abc",
        },
    )
    assert response.status_code == 202, response.text
    identity = response.json()["job_id"]
    job = client.app.state.db.claim()
    payload = json.loads(job["payload"])
    assert payload["other_language"] == "Turkish"
    assert {row["model_id"] for row in payload["selected_models"]} == {MULTILINGUAL}

    class MultilingualPredictor(Predictor):
        # Controlled adapter exercises admission/publication, not checkpoint compatibility.
        def classify(self, model, documents, inputs, device):
            assert not inputs
            return self.predict(model, documents, None, device)

    engine = MultilingualPredictor()
    summary = process_job(job, settings, engine, controlled_stats, lambda _: registry)
    client.app.state.db.finish(identity, summary)
    assert len(engine.calls) == 1
    status = client.get("/api/jobs/" + identity).json()
    assert status["status"] == "COMPLETED", status
    assert status["language"] == "oth" and status["other_language"] == "Turkish"
    assert "OTH" in client.get("/?lang=en").text
    documents = client.get("/api/my/documents").json()
    assert documents["items"][0]["language"] == "oth"


@pytest.mark.parametrize(
    "overrides",
    [
        {"language": "oth"},
        {"language": "oth", "other_language": "  "},
        {"job_name": "x" * 201},
        {"job_name": "line\nbreak"},
        {"other_language": "line\x7fbreak"},
    ],
)
def test_metadata_validation(overrides):
    with pytest.raises(ValidationError):
        Submission(**request_data(**overrides))
