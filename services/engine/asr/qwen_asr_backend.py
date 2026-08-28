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

    DEFAULT_FORCED_ALIGNER = "Qwen/Qwen3-ForcedAligner-0.6B"

    def __init__(self, model_path: str | None = None, forced_aligner_path: str | None = None):
        self._model = None
        self._aligner = None
        self._model_path = model_path
        self._forced_aligner_path = forced_aligner_path or self.DEFAULT_FORCED_ALIGNER

    def _load_model(self) -> None:
        if self._model is not None:
            return

        try:
            import torch
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

        # Check if forced aligner path exists locally
        local_aligner = Path(self._forced_aligner_path)
        if not local_aligner.exists() and not self._forced_aligner_path.startswith("Qwen/"):
             # Fallback to default if local path doesn't exist
             self._forced_aligner_path = self.DEFAULT_FORCED_ALIGNER

        logger.info(f"Loading Qwen3-ASR model from: {self._model_path}")
        logger.info(f"Using forced aligner: {self._forced_aligner_path}")
        
        self._model = Qwen3ASRModel.from_pretrained(
            self._model_path,
            forced_aligner=self._forced_aligner_path,
            forced_aligner_kwargs=dict(
                dtype=torch.bfloat16,
                device_map="auto",
            ),
            dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )
        logger.info("Qwen3-ASR model loaded successfully")

    def _load_aligner(self) -> None:
        if self._aligner is not None:
            return

        try:
            import torch
            from qwen_asr import Qwen3ForcedAligner
        except ImportError as e:
            raise RuntimeError("qwen-asr is required for Qwen3-ASR.") from e

        logger.info(f"Loading Qwen3-ForcedAligner from: {self._forced_aligner_path}")
        self._aligner = Qwen3ForcedAligner.from_pretrained(
            self._forced_aligner_path,
            dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )
        logger.info("Qwen3-ForcedAligner loaded successfully")

    def _preprocess_audio(self, audio_path: Path) -> tuple[np.ndarray, int]:
        audio, sr = librosa.load(
            str(audio_path),
            sr=16000,
            mono=True,
            dtype=np.float32,
        )
        return audio, sr

    def _normalize_result(self, result, is_alignment: bool = False) -> dict:
        """Normalize qwen-asr result to our transcript schema.
        
        Handles forced aligner output where timestamps may be:
        - Center-point (start == end): expanded to 0.2s range
        - Zero (start == end == 0): kept as-is for fallback
        - Normal (start < end): used directly
        """
        # If it's a direct alignment result, it might be a list of segments/words
        if is_alignment:
            items = result
            text = "".join([getattr(item, "text", str(item)) for item in items])
            language = "auto"
        else:
            text = result.text.strip() if result.text else ""
            language = result.language if hasattr(result, "language") and result.language else "auto"
            items = []
            if hasattr(result, "time_stamps") and result.time_stamps:
                ts = result.time_stamps
                # Check if it's a list or an object with items
                if isinstance(ts, list):
                    items = ts
                elif hasattr(ts, "items"):
                    items = ts.items

        segments = []
        words = []
        zero_ts_count = 0
        center_point_count = 0

        prev_end = 0.0
        for i, item in enumerate(items):
            word_text = item.text if hasattr(item, "text") else str(item)
            start_time = float(item.start_time) if hasattr(item, "start_time") else 0.0
            end_time = float(item.end_time) if hasattr(item, "end_time") else start_time
            
            if not word_text.strip():
                continue
            
            # Detect center-point timestamps (start == end, non-zero)
            # Or extremely short durations (< 0.05s)
            if start_time > 0 and abs(start_time - end_time) < 0.05:
                center_point_count += 1
                # Expand to 0.2s range, respecting previous word's end
                # but ensure we don't overlap too much if they are dense
                half_span = 0.1
                start_time = max(prev_end, start_time - half_span)
                end_time = start_time + 0.2
            elif start_time == 0 and end_time == 0:
                zero_ts_count += 1
                start_time = None
                end_time = None
            
            if start_time is not None:
                start_time = round(max(0.0, start_time), 3)
                end_time = round(max(start_time + 0.05, end_time), 3)
                prev_end = end_time
            
            words.append({
                "word": word_text.strip(),
                "start": start_time,
                "end": end_time,
            })
            segments.append({
                "id": f"seg_{i + 1}",
                "text": word_text.strip(),
                "start": start_time,
                "end": end_time,
                "confidence": 1.0,
                "words": [],
            })

        total_words = len(words)
        if total_words > 0:
            zero_pct = zero_ts_count / total_words * 100
            cp_pct = center_point_count / total_words * 100
            if zero_pct > 10:
                logger.warning(
                    "Qwen3-ASR forced aligner: %.0f%% words (%d/%d) have zero timestamps",
                    zero_pct, zero_ts_count, total_words
                )
            if cp_pct > 50 and zero_pct == 0:
                logger.info(
                    "Qwen3-ASR forced aligner: center-point timestamps detected (%.0f%% words, %d/%d). "
                    "Timestamps expanded to 0.2s ranges.",
                    cp_pct, center_point_count, total_words
                )

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

        logger.info(f"Transcribing with Qwen3-ASR (language={qwen_lang or 'auto'}, audio_len={audio.shape[0]/sr:.1f}s)")
        results = self._model.transcribe(
            audio=(audio, sr),
            language=qwen_lang,
            return_time_stamps=True,
        )

        if not results:
            raise RuntimeError("Qwen3-ASR returned empty transcription")

        logger.info("Qwen3-ASR transcription complete")
        normalized = self._normalize_result(results[0])
        return normalized

    def align(
        self,
        audio_path: Path,
        text: str,
        language: str | None = None,
    ) -> dict:
        """Align text directly to audio using Qwen3-ForcedAligner."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._load_aligner()

        audio, sr = self._preprocess_audio(audio_path)
        
        # Map language code to qwen-asr language name
        qwen_lang = "auto"
        if language and language in _LANGUAGE_MAP:
            qwen_lang = _LANGUAGE_MAP[language] or "auto"

        logger.info(f"Aligning with Qwen3-ForcedAligner (language={qwen_lang}, audio_len={audio.shape[0]/sr:.1f}s)")
        
        # Qwen3ForcedAligner.align expects (audio, sr) and text
        results = self._aligner.align(
            audio=(audio, sr),
            text=text,
            language=qwen_lang,
        )

        if not results:
            raise RuntimeError("Qwen3-ForcedAligner returned empty alignment")

        logger.info("Qwen3-ForcedAligner alignment complete")
        # Results is usually a list of word/token items for each input in batch
        normalized = self._normalize_result(results[0], is_alignment=True)
        return normalized
