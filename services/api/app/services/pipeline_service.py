from __future__ import annotations

import json
import threading
from pathlib import Path

from app.services.project_store import ProjectStore, STAGE_NAMES
from services.engine.pipeline import PipelineRunner


class PipelineService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.runner = PipelineRunner(store)
        self._threads: dict[str, threading.Thread] = {}

    def start_full_pipeline(self, project_id: str) -> None:
        self._start(project_id, [])

    def rerun(
        self,
        project_id: str,
        stages: list[str],
        unlocked_only: bool = True,
        transcription_backend: str | None = None,
        language: str | None = None,
    ) -> None:
        payload = self.store.get_project(project_id)
        payload["config"]["unlocked_only"] = unlocked_only
        if transcription_backend in {"openai", "whisper_cpp", "qwen_asr"}:
            payload["transcription_backend"] = transcription_backend
        if language:
            payload["config"]["language"] = language
        self.store.update_project(project_id, payload)
        self._start(project_id, stages)

    def patch_lyrics(self, project_id: str, lyrics_text: str) -> None:
        project = self.store.get_project(project_id)
        project_dir = Path(project["artifacts"]["project_dir"])
        (project_dir / "input" / "lyrics.txt").write_text(lyrics_text, encoding="utf-8")
        project["lyrics_provided"] = True
        project.setdefault("config", {})["force_refresh_edited_lyrics"] = True
        self.store.update_project(project_id, project)
        self._start(project_id, ["acquire_lyrics", "align_lyrics", "render_preview"])

    def refresh_lyrics(self, project_id: str) -> None:
        project = self.store.get_project(project_id)
        project.setdefault("config", {})["force_refresh_edited_lyrics"] = True
        self.store.update_project(project_id, project)
        self._start(project_id, ["align_lyrics", "render_preview"])

    def patch_timing(self, project_id: str, timing_payload: dict) -> None:
        project = self.store.get_project(project_id)
        project_dir = Path(project["artifacts"]["project_dir"])
        edited_path = project_dir / "transcript" / "edited_lyrics.json"
        edited_path.write_text(
            json.dumps(timing_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        project["artifacts"]["edited_lyrics_json"] = str(edited_path)
        
        # Save metadata to project config
        if "title" in timing_payload:
            project.setdefault("config", {})["title"] = timing_payload["title"]
        if "artist" in timing_payload:
            project.setdefault("config", {})["artist"] = timing_payload["artist"]
        if "enable_word_timing" in timing_payload:
            project.setdefault("config", {})["enable_word_timing"] = timing_payload["enable_word_timing"]
            
        self.store.update_project(project_id, project)
        self._start(project_id, ["render_preview"])

    def _start(self, project_id: str, forced_stages: list[str]) -> None:
        if project_id in self._threads and self._threads[project_id].is_alive():
            return

        target = lambda: self.runner.run(project_id, forced_stages=forced_stages)
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self._threads[project_id] = thread
