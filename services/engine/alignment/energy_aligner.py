from __future__ import annotations

import logging
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


def energy_based_alignment(
    audio_path: str,
    lines: list[str],
    sample_rate: int = 44100,
    frame_length: int = 2048,
    hop_length: int = 512,
) -> list[dict]:
    """Align lyrics to audio using energy-based word boundary detection.

    Uses short-time energy to find silence gaps and word boundaries.
    Works well for Korean and other syllabic languages.

    Args:
        audio_path: Path to vocals.wav
        lines: List of lyric lines
        sample_rate: Audio sample rate
        frame_length: FFT frame length
        hop_length: Hop length for STFT

    Returns:
        List of line dicts with timing info
    """
    # Load audio
    audio, sr = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # Compute short-time energy
    frames = _stft_energy(audio, sr, frame_length, hop_length)
    energy = np.sum(frames ** 2, axis=0)
    logger.info("Energy alignment: loaded %.1fs audio, %d samples", len(audio) / sr, len(audio))

    # Normalize energy
    energy = energy / (np.max(energy) + 1e-10)

    # Detect silence regions (energy < threshold)
    threshold = 0.02  # 2% of max energy
    silence_mask = energy < threshold

    # Find boundaries where energy transitions from high to low
    boundaries = _find_transitions(silence_mask, audio.shape[0] // hop_length)
    logger.info("Energy alignment: %d energy frames, threshold=%.4f, found %d boundaries (need %d)",
                len(energy), threshold, len(boundaries), len(lines) * 2)

    # If we don't have enough boundaries, use equal spacing as fallback
    if len(boundaries) < len(lines) * 2:
        logger.info("Energy alignment: insufficient boundaries, using fallback alignment")
        return _fallback_alignment(lines, len(audio) / sr)

    # Use boundaries to allocate time to each line
    return _allocate_lines(lines, boundaries, len(audio) / sr, sr, hop_length)


def _stft_energy(audio: np.ndarray, sr: int, frame_length: int, hop_length: int) -> np.ndarray:
    """Compute short-time energy frames using simple windowing."""
    # Simple rectangular window
    n_frames = 1 + (len(audio) - frame_length) // hop_length
    frames = np.zeros((frame_length, n_frames), dtype=np.float32)

    for i in range(n_frames):
        start = i * hop_length
        end = start + frame_length
        if end <= len(audio):
            frames[:, i] = audio[start:end]

    return frames


def _find_transitions(silence_mask: np.ndarray, n_frames: int) -> list[int]:
    """Find frames where silence transitions occur."""
    transitions = []
    for i in range(1, n_frames):
        if silence_mask[i] != silence_mask[i - 1]:
            transitions.append(i)
    return transitions


def _fallback_alignment(lines: list[str], duration: float) -> list[dict]:
    """Fallback: equal duration allocation."""
    lines_result = []
    span = duration / max(len(lines), 1)

    for idx, text in enumerate(lines):
        start = idx * span
        end = min(duration, start + span)
        lines_result.append({
            "text": text,
            "start": start,
            "end": end,
        })

    return lines_result


def _allocate_lines(
    lines: list[str],
    boundaries: list[int],
    duration: float,
    sr: int,
    hop_length: int,
) -> list[dict]:
    """Allocate time ranges to each line based on detected boundaries."""
    # Group boundaries into line segments
    n_lines = len(lines)

    # Use every other boundary to split into line segments
    line_boundaries = []
    step = max(1, len(boundaries) // (n_lines + 1))

    for i in range(1, n_lines + 1):
        idx = min(i * step, len(boundaries) - 1)
        line_boundaries.append(boundaries[idx])

    # Add end boundary
    n_frames = len(audio) // hop_length
    line_boundaries.append(len(boundaries) - 1 if boundaries else n_frames)

    # Convert frame indices to seconds
    lines_result = []
    for idx, text in enumerate(lines):
        if idx < len(line_boundaries) - 1:
            start_frame = line_boundaries[idx]
            end_frame = line_boundaries[idx + 1]
        elif idx == 0 and len(line_boundaries) > 0:
            start_frame = 0
            end_frame = line_boundaries[0]
        else:
            start_frame = line_boundaries[-1] if line_boundaries else 0
            end_frame = duration * sr // hop_length

        start_time = start_frame * hop_length / sr
        end_time = end_frame * hop_length / sr

        lines_result.append({
            "text": text,
            "start": round(max(0, start_time), 3),
            "end": round(min(duration, end_time), 3),
        })

    return lines_result
