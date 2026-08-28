from __future__ import annotations

import logging
from pathlib import Path

from app.services.project_store import ProjectStore
from services.engine.stages.utils import run_cmd

logger = logging.getLogger(__name__)


def run_normalize_audio(
    project_id: str,
    store: ProjectStore,
    progress_cb=None,
) -> None:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])
    src = Path(project["input_audio"])
    dst = project_dir / "input" / "normalized.wav"

    if progress_cb:
        progress_cb(project_id, "normalize_audio", 20, "Reading audio file...")

    logger.info("Normalizing audio: %s", src)
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ]
    )

    if progress_cb:
        progress_cb(project_id, "normalize_audio", 80, "Normalization complete...")

    logger.info("Normalized audio written: %s", dst)
    project["artifacts"]["normalized_audio"] = str(dst)
    store.update_project(project_id, project)

    if progress_cb:
        progress_cb(project_id, "normalize_audio", 100, "Done")
