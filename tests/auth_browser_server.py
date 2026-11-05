"""Explicit test-only server: real auth/HTTP/storage, controlled scientific predictions."""

import asyncio
from contextlib import asynccontextmanager

from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.main import create_app
from app.services.pipeline import process_job
from tests.test_incremental import controlled_stats


class Predictor:
    def predict(self, model, documents, output, device):
        return [
            {
                "filename": name,
                "label": model["label"],
                "start_span": 0,
                "end_span": min(3, len(text)),
                "text": text[:3],
                "score": 0.8,
            }
            for name, text in documents.items()
        ], {"model_id": model["model_id"]}


def factory():
    settings = Settings()
    if settings.app_env != "test":
        raise RuntimeError("This synthetic server is test-only")
    app = create_app(settings)
    app.state.registry.models["es-disease"]["available"] = True
    original = app.router.lifespan_context

    def step():
        app.state.db.heartbeat()
        record = app.state.db.claim()
        if record:
            summary = process_job(
                record,
                settings,
                Predictor(),
                controlled_stats,
                registry_factory=lambda _: app.state.registry,
            )
            app.state.db.finish(record["id"], summary)

    @asynccontextmanager
    async def lifespan(application):
        async with original(application):

            async def work():
                while True:
                    await run_in_threadpool(step)
                    await asyncio.sleep(0.1)

            task = asyncio.create_task(work())
            try:
                yield
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    app.router.lifespan_context = lifespan
    return app
