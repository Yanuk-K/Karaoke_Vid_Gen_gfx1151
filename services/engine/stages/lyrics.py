from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.project_store import ProjectStore
from services.engine.asr.openai_whisper_backend import OpenAIWhisperBackend
from services.engine.asr.qwen_asr_backend import QwenASRBackend
from services.engine.asr.whisper_cpp_backend import WhisperCppBackend
from services.engine.stages.utils import write_json

logger = logging.getLogger(__name__)


def run_acquire_lyrics(
    project_id: str,
    store: ProjectStore,
    progress_cb=None,
) -> None:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])
    lyrics_txt = project_dir / "input" / "lyrics.txt"
    out_path = project_dir / "transcript" / "raw_transcript.json"

    # Get transcription backend preference
    transcription_backend = project.get("transcription_backend", "openai")
    if transcription_backend not in ["openai", "whisper_cpp", "qwen_asr"]:
        transcription_backend = "openai"

    vocals = Path(project["artifacts"].get("vocals", ""))
    if not vocals.exists():
        raise FileNotFoundError(
            f"Vocals stem not found for transcription: {vocals}. "
            "Run separation first."
        )

    official_lyrics_lines: list[str] = []
    if lyrics_txt.exists() and lyrics_txt.read_text(encoding="utf-8").strip():
        text = lyrics_txt.read_text(encoding="utf-8").strip()
        official_lyrics_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not official_lyrics_lines:
            official_lyrics_lines = [text]

    if official_lyrics_lines and progress_cb:
        progress_cb(project_id, "acquire_lyrics", 10, "Official lyrics detected, transcribing for timing...")

    if transcription_backend == "openai":
        try:
            if progress_cb:
                progress_cb(project_id, "acquire_lyrics", 20, "Running OpenAI Whisper transcription...")

            backend = OpenAIWhisperBackend()
            
            # Use official lyrics as initial prompt to guide recognition
            prompt = None
            if official_lyrics_lines:
                # Use only the first 200 chars for style/spelling context
                # without biasing the entire transcription too much.
                full_text = " ".join(official_lyrics_lines)
                prompt = full_text[:200]

            payload = backend.transcribe(vocals, prompt=prompt)

            if official_lyrics_lines:
                payload["official_lyrics_lines"] = official_lyrics_lines

            if progress_cb:
                progress_cb(project_id, "acquire_lyrics", 80, "Transcription complete...")

            write_json(out_path, payload)
            logger.info(f"OpenAI Whisper transcription successful: {len(payload.get('segments', []))} segments")

        except Exception as e:
            logger.error(f"OpenAI Whisper failed: {e}")
            payload = {
                "source": "transcription_failed",
                "backend": "openai",
                "error": str(e),
                "segments": [],
            }
            if official_lyrics_lines:
                payload["official_lyrics_lines"] = official_lyrics_lines
            write_json(out_path, payload)
            raise RuntimeError(f"OpenAI Whisper transcription failed: {e}") from e
    elif transcription_backend == "whisper_cpp":
        # Use whisper.cpp
        try:
            if progress_cb:
                progress_cb(project_id, "acquire_lyrics", 20, "Running whisper.cpp transcription...")

            backend = WhisperCppBackend()
            payload = backend.transcribe(vocals, out_path)

            if official_lyrics_lines:
                payload["official_lyrics_lines"] = official_lyrics_lines

            if progress_cb:
                progress_cb(project_id, "acquire_lyrics", 80, "Transcription complete...")

            if not payload.get("segments") and not payload.get("text"):
                raise RuntimeError(
                    "whisper.cpp returned empty transcription. "
                    "Check model/configuration or provide lyrics manually."
                )

            write_json(out_path, payload)

        except Exception as e:
            logger.error(f"whisper.cpp failed: {e}")
            payload = {
                "source": "transcription_failed",
                "backend": "whisper_cpp",
                "error": str(e),
                "segments": [],
            }
            if official_lyrics_lines:
                payload["official_lyrics_lines"] = official_lyrics_lines
            write_json(out_path, payload)
            raise RuntimeError(f"whisper.cpp transcription failed: {e}") from e
    else:
        # Use Qwen3-ASR
        try:
            if progress_cb:
                progress_cb(project_id, "acquire_lyrics", 20, "Running Qwen3-ASR transcription...")

            from app.core.config import QWEN_ASR_MODEL_PATH

            backend = QwenASRBackend(model_path=QWEN_ASR_MODEL_PATH or None)
            payload = backend.transcribe(vocals, language=project.get("config", {}).get("language"))

            if official_lyrics_lines:
                payload["official_lyrics_lines"] = official_lyrics_lines

            if progress_cb:
                progress_cb(project_id, "acquire_lyrics", 80, "Transcription complete...")

            if not payload.get("segments") and not payload.get("text"):
                raise RuntimeError(
                    "Qwen3-ASR returned empty transcription. "
                    "Check model/configuration or provide lyrics manually."
                )

            write_json(out_path, payload)

        except Exception as e:
            logger.error(f"Qwen3-ASR failed: {e}")
            payload = {
                "source": "transcription_failed",
                "backend": "qwen_asr",
                "error": str(e),
                "segments": [],
            }
            if official_lyrics_lines:
                payload["official_lyrics_lines"] = official_lyrics_lines
            write_json(out_path, payload)
            raise RuntimeError(f"Qwen3-ASR transcription failed: {e}") from e

    if progress_cb:
        progress_cb(project_id, "acquire_lyrics", 100, "Lyrics acquired")

    project["artifacts"]["raw_transcript"] = str(out_path)
    store.update_project(project_id, project)
