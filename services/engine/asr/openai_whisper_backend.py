from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import openai


class OpenAIWhisperBackend:
    """Transcribe audio using OpenAI Whisper API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = openai.OpenAI(api_key=self.api_key)

    def _prepare_mp3_for_upload(self, audio_path: Path) -> Path:
        """Create a temporary compact MP3 for OpenAI upload."""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "64k",
            str(tmp_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"ffmpeg MP3 conversion failed: {stderr or 'unknown error'}") from exc
        return tmp_path

    @staticmethod
    def _segment_value(segment: object, key: str, default: object) -> object:
        if isinstance(segment, dict):
            return segment.get(key, default)
        return getattr(segment, key, default)

    def transcribe(self, audio_path: Path, language: str | None = None, prompt: str | None = None) -> dict:
        """Transcribe audio file using OpenAI Whisper.

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., 'ko', 'en'). None for auto-detect.
            prompt: Optional initial prompt to guide transcription (useful for known lyrics).

        Returns:
            Transcript dict with segments
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        upload_path = audio_path
        temp_path: Path | None = None
        try:
            # Always upload MP3 to keep payload small and consistent.
            if audio_path.suffix.lower() != ".mp3":
                temp_path = self._prepare_mp3_for_upload(audio_path)
                upload_path = temp_path

            # OpenAI Whisper has a 25MB file size limit
            if upload_path.stat().st_size > 25 * 1024 * 1024:
                raise ValueError(
                    f"Audio file too large ({upload_path.stat().st_size / 1024 / 1024:.1f}MB). "
                    "Max size is 25MB. Please split the file or use whisper.cpp instead."
                )

            with open(upload_path, "rb") as f:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                    prompt=prompt,
                    response_format="verbose_json",
                    timestamp_granularities=["segment", "word"],
                )
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

        # Convert OpenAI response to our format
        segments = []
        for i, seg in enumerate(getattr(response, "segments", []) or []):
            text = str(self._segment_value(seg, "text", "")).strip()
            start = float(self._segment_value(seg, "start", 0.0) or 0.0)
            end = float(self._segment_value(seg, "end", start) or start)
            
            # Extract word-level timestamps if available
            words = []
            for word_seg in getattr(seg, "words", []) or []:
                words.append({
                    "word": str(self._segment_value(word_seg, "word", "")).strip(),
                    "start": float(self._segment_value(word_seg, "start", 0.0) or 0.0),
                    "end": float(self._segment_value(word_seg, "end", 0.0) or 0.0),
                })

            segments.append(
                {
                    "id": f"seg_{i+1}",
                    "text": text,
                    "start": start,
                    "end": end,
                    "confidence": 1.0,
                    "words": words,
                }
            )

        transcript_text = str(getattr(response, "text", "") or "").strip()
        if not transcript_text and segments:
            transcript_text = " ".join(seg["text"] for seg in segments).strip()

        return {
            "source": "openai_whisper",
            "text": transcript_text,
            "segments": segments,
            "language": getattr(response, "language", "auto"),
            "upload_format": "mp3",
        }
