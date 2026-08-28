from __future__ import annotations

import logging
import numpy as np
import soundfile as sf
import torch
import torchcrepe

logger = logging.getLogger(__name__)


def extract_f0(
    audio_path: str | Path,
    sample_rate: int = 44100,
    threshold: float = 0.22,
) -> dict:
    """Extract F0 contour using torchcrepe.

    Returns dict with:
      - sample_rate: F0 sample rate (100 Hz default)
      - values: list of {time, f0_hz, voiced}
    """
    audio, sr = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    logger.info("F0 extraction: loaded %.1fs audio, %d samples at %d Hz", len(audio) / sr, len(audio), sr)

    # Normalize
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak

    # Convert to tensor, add batch dimension (torchcrepe expects shape (1, time))
    audio_tensor = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)

    # Extract F0 with torchcrepe using the predict function
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # hop_length in samples: 10ms at 44100 Hz = 441 samples
    hop_samples = max(1, int(0.01 * sr))
    f0_hz, periodicity = torchcrepe.predict(
        audio_tensor,
        sr,
        hop_length=hop_samples,
        fmin=50.0,
        fmax=1100.0,
        model="full",
        batch_size=512,
        device=device,
        return_periodicity=True,
    )

    f0_hz = f0_hz.squeeze(0)
    periodicity = periodicity.squeeze(0)

    # Threshold unvoiced frames using periodicity confidence
    voiced_mask = (periodicity >= threshold) & (f0_hz > 0)
    f0_hz = torch.where(voiced_mask, f0_hz, torch.zeros_like(f0_hz))

    # Build values list
    hop_length = hop_samples
    values = []
    for i in range(len(f0_hz)):
        time = i * hop_length / sr
        f0_val = f0_hz[i].item()
        voiced = f0_val > 0

        values.append({
            "time": round(time, 4),
            "f0_hz": round(f0_val, 2) if voiced else 0.0,
            "voiced": voiced,
        })

    voiced_count = sum(1 for v in values if v["voiced"])
    voiced_pct = voiced_count / len(values) * 100 if values else 0
    logger.info("F0 extraction complete: %d frames, %.1f%% voiced", len(values), voiced_pct)

    return {
        "sample_rate": 100,
        "values": values,
    }


def f0_to_notes(f0_data: dict, min_note_duration: float = 0.05) -> list[dict]:
    """Convert F0 contour to MIDI note events.

    Args:
        f0_data: Output from extract_f0()
        min_note_duration: Minimum note length in seconds (merge short fragments)

    Returns:
        List of note dicts with pitch, start, end, velocity, confidence
    """
    values = f0_data["values"]
    if not values:
        return []

    # Find voiced regions
    notes = []
    current_note = None

    for i, v in enumerate(values):
        if v["voiced"]:
            if current_note is None:
                # Start new note
                current_note = {
                    "start_time": v["time"],
                    "end_time": v["time"] + 0.01,
                    "f0_sum": v["f0_hz"],
                    "count": 1,
                    "confidence_sum": v["f0_hz"] / 1100.0,  # normalize confidence
                }
            else:
                prev_avg = current_note["f0_sum"] / max(current_note["count"], 1)
                jump = _semitone_distance(prev_avg, v["f0_hz"])
                if jump >= 0.8:
                    _finalize_note(current_note, min_note_duration)
                    notes.append(current_note)
                    current_note = {
                        "start_time": v["time"],
                        "end_time": v["time"] + 0.01,
                        "f0_sum": v["f0_hz"],
                        "count": 1,
                        "confidence_sum": v["f0_hz"] / 1100.0,
                    }
                else:
                    current_note["end_time"] = v["time"] + 0.01
                    current_note["f0_sum"] += v["f0_hz"]
                    current_note["count"] += 1
                    current_note["confidence_sum"] += v["f0_hz"] / 1100.0
        else:
            if current_note is not None:
                # End current note
                _finalize_note(current_note, min_note_duration)
                notes.append(current_note)
                current_note = None

    # Handle trailing voiced region
    if current_note is not None:
        _finalize_note(current_note, min_note_duration)
        notes.append(current_note)

    # Merge short fragments
    notes = _merge_short_notes(notes, min_note_duration)

    # Convert to MIDI note format
    midi_notes = []
    for note in notes:
        avg_f0 = note["f0_sum"] / note["count"]
        midi_pitch = _f0_to_midi_pitch(avg_f0)
        velocity = max(1, min(127, int(60 + note["confidence_sum"] / note["count"] * 60)))

        midi_notes.append({
            "pitch": midi_pitch,
            "start": round(note["start_time"], 3),
            "end": round(note["end_time"], 3),
            "velocity": velocity,
            "confidence": round(note["confidence_sum"] / note["count"], 3),
        })

    if midi_notes:
        pitches = [n["pitch"] for n in midi_notes]
        logger.info("F0 -> MIDI notes: %d notes, pitch range %d-%d (MIDI)", len(midi_notes), min(pitches), max(pitches))
    else:
        logger.info("F0 -> MIDI notes: 0 notes (no voiced regions detected)")

    return midi_notes


def _finalize_note(note: dict, min_duration: float) -> None:
    """Ensure note meets minimum duration requirement."""
    duration = note["end_time"] - note["start_time"]
    if duration < min_duration:
        # Extend to minimum
        note["end_time"] = note["start_time"] + min_duration


def _merge_short_notes(notes: list, min_duration: float) -> list:
    """Merge adjacent notes that are too short."""
    if len(notes) <= 1:
        return notes

    merged = [notes[0]]
    for note in notes[1:]:
        prev = merged[-1]
        gap = note["start_time"] - prev["end_time"]
        prev_f0 = prev["f0_sum"] / max(prev["count"], 1)
        note_f0 = note["f0_sum"] / max(note["count"], 1)
        pitch_diff = _semitone_distance(prev_f0, note_f0)

        if (
            gap < 0.02
            and (note["end_time"] - prev["start_time"]) < min_duration * 3
            and pitch_diff < 0.5
        ):
            # Merge: extend previous note
            prev["end_time"] = note["end_time"]
            prev["f0_sum"] += note["f0_sum"]
            prev["count"] += note["count"]
            prev["confidence_sum"] += note["confidence_sum"]
        else:
            merged.append(note)

    return merged


def _f0_to_midi_pitch(f0_hz: float) -> int:
    """Convert frequency in Hz to MIDI note number (rounded)."""
    if f0_hz <= 0:
        return 60  # default middle C
    midi = 69 + 12 * np.log2(f0_hz / 440.0)
    return int(round(midi))


def _semitone_distance(f0_a: float, f0_b: float) -> float:
    if f0_a <= 0 or f0_b <= 0:
        return 999.0
    return abs(12.0 * np.log2(f0_b / f0_a))
