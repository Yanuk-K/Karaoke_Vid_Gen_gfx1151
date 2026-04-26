from __future__ import annotations

import logging
from pathlib import Path

import librosa
import numpy as np

logger = logging.getLogger(__name__)

# Language mapping: frontend language codes -> qwen-asr language names
_LANGUAGE_MAP = {
    "auto": None,
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "yue": "Cantonese",
}


class QwenASRBackend:
    """Transcribe audio using Qwen3-ASR-1.7B via the qwen-asr package."""

    def __init__(self, model_path: str | None = None):
        self._model = None
        self._model_path = model_path

    def _load_model(self) -> None:
        if self._model is not None:
            return

        try:
            from qwen_asr import Qwen3ASRModel
        except ImportError as e:
            raise RuntimeError(
                "qwen-asr is required for Qwen3-ASR. "
                "Install it with: pip install qwen-asr"
            ) from e

        if self._model_path is None:
            self._model_path = "Qwen/Qwen3-ASR-1.7B"
            logger.info(
                "QWEN_ASR_MODEL_PATH not set, auto-downloading Qwen/Qwen3-ASR-1.7B from HuggingFace Hub..."
            )

        logger.info(f"Loading Qwen3-ASR model from: {self._model_path}")
        self._model = Qwen3ASRModel.from_pretrained(
            self._model_path,
            trust_remote_code=True,
        )
        logger.info("Qwen3-ASR model loaded successfully")

    def _preprocess_audio(self, audio_path: Path) -> tuple[np.ndarray, int]:
        audio, sr = librosa.load(
            str(audio_path),
            sr=16000,
            mono=True,
            dtype=np.float32,
        )
        return audio, sr

    def _normalize_result(self, result) -> dict:
        """Normalize qwen-asr result to our transcript schema."""
        text = result.text.strip() if result.text else ""
        language = result.language if hasattr(result, "language") and result.language else "auto"

        segments = []
        words = []

        # Check if we have timestamp information
        if hasattr(result, "time_stamps") and result.time_stamps:
            time_stamps = result.time_stamps
            if isinstance(time_stamps, list) and len(time_stamps) > 0:
                for i, ts in enumerate(time_stamps):
                    if isinstance(ts, tuple) and len(ts) >= 2:
                        word_text = ts[0] if isinstance(ts[0], str) else str(ts[0])
                        start_time = float(ts[1]) if len(ts) > 1 else 0.0
                        end_time = float(ts[2]) if len(ts) > 2 else start_time
                        if word_text.strip():
                            words.append({
                                "word": word_text.strip(),
                                "start": round(max(0.0, start_time), 3),
                                "end": round(max(start_time, end_time), 3),
                            })
                            segments.append({
                                "id": f"seg_{i + 1}",
                                "text": word_text.strip(),
                                "start": round(max(0.0, start_time), 3),
                                "end": round(max(start_time, end_time), 3),
                                "confidence": 1.0,
                                "words": [],
                            })

        return {
            "source": "qwen_asr",
            "backend": "qwen_asr",
            "text": text,
            "segments": segments,
            "words": words,
            "language": language,
        }

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        prompt: str | None = None,
    ) -> dict:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._load_model()

        audio, sr = self._preprocess_audio(audio_path)

        # Map language code to qwen-asr language name
        qwen_lang = None
        if language and language in _LANGUAGE_MAP:
            qwen_lang = _LANGUAGE_MAP[language]

        logger.info(f"Transcribing with Qwen3-ASR (language={qwen_lang or 'auto'})")
        results = self._model.transcribe(
            audio=(audio, sr),
            language=qwen_lang,
            return_time_stamps=True,
        )

        if not results:
            raise RuntimeError("Qwen3-ASR returned empty transcription")

        normalized = self._normalize_result(results[0])
        return normalized
