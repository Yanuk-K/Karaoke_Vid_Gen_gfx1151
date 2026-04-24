from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.services.project_store import ProjectStore, STAGE_NAMES
from services.engine.stages.align_lyrics import run_align_lyrics
from services.engine.stages.extract_melody import run_extract_melody
from services.engine.stages.lyrics import run_acquire_lyrics
from services.engine.stages.normalize_audio import run_normalize_audio
from services.engine.stages.render_preview import run_render_preview
from services.engine.stages.separate_stems import run_separate_stems

logger = logging.getLogger(__name__)

STAGE_FUNCS = {
    "normalize_audio": run_normalize_audio,
    "separate_stems": run_separate_stems,
    "acquire_lyrics": run_acquire_lyrics,
    "align_lyrics": run_align_lyrics,
    "extract_melody": run_extract_melody,
    "render_preview": run_render_preview,
}


class PipelineRunner:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self._stop_event = threading.Event()

    def run(self, project_id: str, forced_stages: list[str] | None = None) -> None:
        forced_set = set(forced_stages or [])
        try:
            project = self.store.get_project(project_id)
            project["status"] = "running"
            self.store.update_project(project_id, project)

            total_stages = len(STAGE_NAMES)
            completed_count = 0

            for stage in STAGE_NAMES:
                if self._stop_event.is_set():
                    break

                if forced_set and stage not in forced_set:
                    continue

                project = self.store.get_project(project_id)
                if not forced_set and project["stages"][stage]["status"] == "done":
                    logger.info(f"Skipping {stage} (cached)")
                    self.store.set_stage(project_id, stage, "skipped", "cached")
                    completed_count += 1
                    self._update_progress(project_id, completed_count, total_stages)
                    continue

                logger.info(f"Running stage: {stage}")
                self.store.set_stage(project_id, stage, "running")

                # Run stage with progress tracking
                try:
                    STAGE_FUNCS[stage](project_id, self.store, progress_cb=self._stage_progress)
                    logger.info(f"Completed stage: {stage}")
                    self.store.set_stage(project_id, stage, "done")
                    completed_count += 1
                except Exception as e:
                    logger.error(f"Failed stage {stage}: {e}", exc_info=True)
                    self.store.set_stage(project_id, stage, "failed", str(e))
                    logger.info(f"Stopping pipeline after stage '{stage}' failed")
                    break

                self._update_progress(project_id, completed_count, total_stages)

            project = self.store.get_project(project_id)
            failed = any(s["status"] == "failed" for s in project["stages"].values())
            if not failed and not self._stop_event.is_set():
                logger.info("Pipeline completed successfully")
                self.store.mark_completed(project_id)
            else:
                logger.info("Pipeline finished with errors")

        except Exception as exc:
            logger.error(f"Pipeline failed: {exc}", exc_info=True)
            self.store.mark_failed(project_id, str(exc))

    def stop(self) -> None:
        self._stop_event.set()

    def _stage_progress(self, project_id: str, stage: str, percent: float, message: str = "") -> None:
        """Update progress within a stage (0-100)."""
        try:
            project = self.store.get_project(project_id)
            stage_info = project["stages"].get(stage, {})
            stage_info["progress"] = round(percent, 1)
            stage_info["message"] = message or stage_info.get("message", "")
            project["stages"][stage] = stage_info
            self.store.update_project(project_id, project)
        except Exception:
            pass  # Don't let progress updates crash the pipeline

    def _update_progress(self, project_id: str, completed: int, total: int) -> None:
        """Update overall pipeline progress."""
        try:
            project = self.store.get_project(project_id)
            percent = int((completed / max(total, 1)) * 100)
            project["progress"] = percent
            self.store.update_project(project_id, project)
        except Exception:
            pass
