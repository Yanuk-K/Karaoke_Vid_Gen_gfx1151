from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProjectStatus = Literal["queued", "running", "completed", "failed"]


class ProjectCreateResponse(BaseModel):
    project_id: str
    status: ProjectStatus


class StageProgress(BaseModel):
    status: Literal["pending", "running", "done", "failed", "skipped"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str = ""


class ProjectRead(BaseModel):
    project_id: str
    status: ProjectStatus
    current_stage: str | None = None
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    transcription_backend: Literal["openai", "whisper_cpp", "qwen_asr"] | None = None
    artifacts: dict[str, str]
    stages: dict[str, StageProgress]
    errors: list[str]
    config: dict


class RerunRequest(BaseModel):
    stages: list[str]
    unlocked_only: bool = True
    transcription_backend: Literal["openai", "whisper_cpp", "qwen_asr"] | None = None
    language: str | None = None


class LyricsPatchRequest(BaseModel):
    lyrics_text: str


class LyricsRead(BaseModel):
    lyrics_text: str
    source: Literal["provided", "edited_lyrics", "raw_transcript", "empty"]
