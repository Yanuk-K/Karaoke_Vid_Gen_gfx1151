from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import PROJECTS_DIR

STAGE_NAMES = [
    "normalize_audio",
    "separate_stems",
    "acquire_lyrics",
    "align_lyrics",
    "extract_melody",
    "render_preview",
]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProjectStore:
    def __init__(self, projects_dir: Path = PROJECTS_DIR) -> None:
        self.projects_dir = projects_dir
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def create_project(
        self,
        audio_file: UploadFile,
        lyrics_text: str | None,
        transcription_backend: str = "openai",
        language: str | None = None,
    ) -> dict:
        project_id = str(uuid.uuid4())
        project_dir = self.projects_dir / project_id
        (project_dir / "input").mkdir(parents=True)
        (project_dir / "stems").mkdir()
        (project_dir / "transcript").mkdir()
        (project_dir / "melody").mkdir()
        (project_dir / "render").mkdir()

        suffix = Path(audio_file.filename or "song.wav").suffix or ".wav"
        input_path = project_dir / "input" / f"song{suffix}"
        with input_path.open("wb") as f:
            shutil.copyfileobj(audio_file.file, f)

        lyrics_path = project_dir / "input" / "lyrics.txt"
        if lyrics_text:
            lyrics_path.write_text(lyrics_text, encoding="utf-8")

        stages = {name: {"status": "pending", "message": ""} for name in STAGE_NAMES}
        now = now_iso()
        config: dict = {
            "countdown_offset": 2.0,
            "next_line_lead_time": 0.9,
            "title": "",
            "artist": "",
        }
        if language:
            config["language"] = language
        payload = {
            "project_id": project_id,
            "status": "queued",
            "current_stage": None,
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "input_audio": str(input_path),
            "lyrics_provided": bool(lyrics_text),
            "transcription_backend": transcription_backend,
            "artifacts": {
                "project_dir": str(project_dir),
            },
            "stages": stages,
            "errors": [],
            "config": config,
        }
        self._write_project(project_id, payload)
        return payload

    def get_project(self, project_id: str) -> dict:
        project_path = self.projects_dir / project_id / "project.json"
        if not project_path.exists():
            raise FileNotFoundError(project_id)
        return json.loads(project_path.read_text(encoding="utf-8"))

    def update_project(self, project_id: str, payload: dict) -> dict:
        payload["updated_at"] = now_iso()
        self._write_project(project_id, payload)
        return payload

    def set_stage(
        self,
        project_id: str,
        stage_name: str,
        status: str,
        message: str = "",
    ) -> dict:
        project = self.get_project(project_id)
        stage = project["stages"][stage_name]
        stage["status"] = status
        stage["message"] = message
        if status == "running":
            stage["started_at"] = now_iso()
            project["current_stage"] = stage_name
            project["status"] = "running"
        elif status in {"done", "failed", "skipped"}:
            stage["finished_at"] = now_iso()

        done_count = sum(
            1
            for s in project["stages"].values()
            if s["status"] in {"done", "skipped"}
        )
        project["progress"] = int((done_count / len(STAGE_NAMES)) * 100)
        return self.update_project(project_id, project)

    def mark_completed(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        project["status"] = "completed"
        project["current_stage"] = None
        project["progress"] = 100
        return self.update_project(project_id, project)

    def mark_failed(self, project_id: str, error: str) -> dict:
        project = self.get_project(project_id)
        project["status"] = "failed"
        project["errors"].append(error)
        return self.update_project(project_id, project)

    def _write_project(self, project_id: str, payload: dict) -> None:
        project_path = self.projects_dir / project_id / "project.json"
        project_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
