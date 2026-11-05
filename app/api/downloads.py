"""Private archive, table and statistics downloads."""

import json

from fastapi import APIRouter
from fastapi.responses import FileResponse


def router(service):
    api = APIRouter()

    @api.get("/api/jobs/{token}/download/brat", response_class=FileResponse)
    def brat(token: str):
        return FileResponse(
            service.result_path(token, "results.zip"),
            filename="ner_results_partial.zip"
            if service.available(token)["status"] == "COMPLETED_WITH_ERRORS"
            else "ner_results.zip",
            media_type="application/zip",
        )

    @api.get("/api/jobs/{token}/download/tsv", response_class=FileResponse)
    def tsv(token: str):
        return FileResponse(
            service.result_path(token, "annotations.tsv"),
            filename="annotations_partial.tsv"
            if service.available(token)["status"] == "COMPLETED_WITH_ERRORS"
            else "annotations.tsv",
            media_type="text/tab-separated-values",
        )

    @api.get("/api/jobs/{token}/statistics")
    def statistics(token: str):
        return json.loads(service.result_path(token, "statistics.json").read_text())

    return api
