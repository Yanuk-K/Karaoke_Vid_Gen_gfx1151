from __future__ import annotations

from app.services.pipeline_service import PipelineService
from app.services.project_store import ProjectStore

STORE = ProjectStore()
PIPELINE = PipelineService(STORE)


def get_store() -> ProjectStore:
    return STORE


def get_pipeline_service() -> PipelineService:
    return PIPELINE
