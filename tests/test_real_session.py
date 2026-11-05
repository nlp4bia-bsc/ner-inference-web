from app.services.inference import NerLabAdapter, NerLabSession
from tests.test_real_inference import build_checkpoint


def test_reused_session_matches_upstream_public_api(tmp_path):
    checkpoint = build_checkpoint(tmp_path)
    model = {
        "model_dir": str(checkpoint),
        "model_id": "synthetic",
        "label": "DISEASE",
        "language": "es",
        "checkpoint_sha256": "test",
        "version": "fixture",
    }
    documents = {"a.txt": "Cancer.\r\n", "b.txt": "Cancer."}
    expected, _ = NerLabAdapter().predict(model, documents, tmp_path / "public", "cpu")
    session = NerLabSession(1)
    actual, first = session.predict(model, documents, tmp_path / "session", "cpu")
    again, second = session.predict(model, documents, tmp_path / "session2", "cpu")
    assert actual == expected == again
    assert first["checkpoint_loaded"] is True
    assert second["checkpoint_loaded"] is False
    assert len(session.cache) == 1
    session.close()
    assert not session.cache
