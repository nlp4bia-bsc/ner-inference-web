"""Reproducible mechanics benchmark; controlled predictor is not a clinical NER benchmark."""

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
import zipfile
from pathlib import Path
from unittest.mock import patch


def case(count, size, batch, baseline=False):
    from app.api.schemas import Submission
    from app.config import Settings
    from app.main import create_app
    from app.permissions.policies import user
    from app.persistence.progress import ProgressRepository
    from app.services.pipeline import process_job
    from tests.auth_helpers import AccountClient as TestClient
    from tests.test_incremental import Predictor, controlled_stats

    with tempfile.TemporaryDirectory(prefix="ner-benchmark-") as temporary:
        root = Path(temporary)
        archive_path = root / "corpus.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as archive:
            for i in range(count):
                archive.writestr(f"folder/{i:04}.txt", b"a" * size)
        settings = Settings(
            storage_root=root / "data",
            inference_document_batch_size=batch,
            min_free_disk_mb=0,
            app_env="test",
            cookie_secure=False,
            mail_backend="memory",
        )
        app = create_app(settings)
        app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
        client = TestClient(app)
        client.__enter__()
        with app.state.db.connect() as c:
            c.execute("UPDATE users SET access_tier='UNLIMITED' WHERE id=?", (user()["id"],))
        user()["access_tier"] = "UNLIMITED"
        tracemalloc.start()
        started = time.perf_counter()
        if baseline:
            source = subprocess.check_output(
                ["git", "show", "9c95bb5:app/services/documents.py"], text=True
            )
            namespace = {}
            # trusted source from pinned historical git revision; benchmark only
            exec(compile(source, "baseline-documents.py", "exec"), namespace)  # nosec B102
            data = namespace["load_documents"](
                [("corpus.zip", archive_path.read_bytes())], settings
            )
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            client.__exit__(None, None, None)
            return {
                "mode": "v2-ingestion",
                "documents": len(data),
                "admission_seconds": time.perf_counter() - started,
                "upload_peak_python_bytes": peak,
                "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        form = Submission(
            submitter_name="Synthetic benchmark",
            submitter_email="bench@example.org",
            language="es",
            entities=["DISEASE"],
        )
        with archive_path.open("rb") as stream:
            accepted = app.state.jobs.submit_streams(
                form, [("corpus.zip", stream)], "bench", "ZIP_ENTRY"
            )
        admission = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        job = app.state.db.claim()
        latencies = []
        publications = []
        origin = time.perf_counter()
        original = ProgressRepository.publish

        def observed(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            publications.append(time.perf_counter() - origin)
            return result

        def during(model, documents):
            before = time.perf_counter()
            response = client.get("/api/jobs/" + accepted["token"] + "/progress")
            latencies.append(time.perf_counter() - before)
            assert response.status_code == 200

        class BenchmarkPredictor(Predictor):
            def predict(self, *args, **kwargs):
                spans, meta = super().predict(*args, **kwargs)
                for span in spans:
                    span["text"] = span["text"][:3]
                return spans, meta

        with patch.object(ProgressRepository, "publish", observed):
            result = process_job(
                job,
                settings,
                BenchmarkPredictor(during),
                controlled_stats,
                lambda _: app.state.registry,
            )
        total = time.perf_counter() - origin
        app.state.db.finish(job["id"], result)
        before = time.perf_counter()
        client.get("/api/jobs/" + accepted["token"] + "/documents?limit=50")
        listing = time.perf_counter() - before
        intervals = [b - a for a, b in zip(publications, publications[1:])]
        client.__exit__(None, None, None)
        return {
            "mode": "v3-microbatch",
            "documents": count,
            "bytes_per_document": size,
            "microbatch": batch,
            "admission_seconds": admission,
            "upload_peak_python_bytes": peak,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "first_document_seconds": publications[0],
            "median_publication_interval_seconds": statistics.median(intervals) if intervals else 0,
            "total_worker_seconds": total,
            "export_seconds": result["export_seconds"],
            "zip_seconds": result["zip_seconds"],
            "http_progress_p95_seconds": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
            "document_listing_seconds": listing,
            "model_initialization_seconds": None,
            "note": "Controlled predictor/statistics; no clinical model throughput claim",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=int, default=1000)
    parser.add_argument("--bytes", type=int, default=16384)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--case", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--real-model", action="store_true")
    parser.add_argument("--output", default="work/benchmark-v3.json")
    args = parser.parse_args()
    if args.case:
        print(json.dumps(case(args.documents, args.bytes, args.batch, args.baseline)))
        return
    results = []
    for baseline, batch in [(True, 32), (False, 8), (False, 32), (False, 64)]:
        command = [
            sys.executable,
            "-m",
            "scripts.benchmark_v3",
            "--case",
            "--documents",
            str(args.documents),
            "--bytes",
            str(args.bytes),
            "--batch",
            str(batch),
        ]
        if baseline:
            command.append("--baseline")
        results.append(json.loads(subprocess.check_output(command, text=True)))
    result = {
        "hardware": {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        "cases": results,
    }
    if args.real_model:
        from app.services.inference import NerLabSession
        from tests.test_real_inference import build_checkpoint

        with tempfile.TemporaryDirectory() as temp:
            path = build_checkpoint(Path(temp))
            model = {
                "model_dir": str(path),
                "model_id": "synthetic-test-only",
                "language": "es",
                "label": "DISEASE",
            }
            engine = NerLabSession(1)
            _, cold = engine.predict(model, {"a": "Cancer."}, Path(temp) / "cold", "cpu")
            _, warm = engine.predict(model, {"a": "Cancer."}, Path(temp) / "warm", "cpu")
            engine.close()
            result["tiny_cpu_session"] = {
                "cold": cold,
                "warm": warm,
                "note": "Random tiny BERT, not a clinical checkpoint",
            }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
