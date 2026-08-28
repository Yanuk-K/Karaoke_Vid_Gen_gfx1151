from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


def synthesize_melody_wav(
    f0_payload: dict,
    output_path: Path,
    sample_rate: int = 44100,
    gain_db: float = -14.0,
    exclusion_ranges: list[dict] | None = None,
) -> None:
    values = f0_payload.get("values", [])
    if not values:
        sf.write(output_path, np.zeros((sample_rate, 2), dtype=np.float32), sample_rate)
        return

    end_time = float(values[-1].get("time", 0.0)) + 0.2
    n_samples = max(1, int(end_time * sample_rate))

    f0_track = np.zeros(n_samples, dtype=np.float32)
    for i, frame in enumerate(values):
        t0 = float(frame.get("time", 0.0))
        t1 = float(values[i + 1].get("time", t0 + 0.01)) if i + 1 < len(values) else t0 + 0.01
        start = max(0, min(n_samples, int(t0 * sample_rate)))
        end = max(start + 1, min(n_samples, int(t1 * sample_rate)))
        f0 = float(frame.get("f0_hz", 0.0)) if frame.get("voiced") else 0.0
        if f0 > 0:
            f0_track[start:end] = f0

    # Apply exclusion ranges
    if exclusion_ranges:
        for r in exclusion_ranges:
            s_idx = max(0, int(float(r["start"]) * sample_rate))
            e_idx = max(s_idx, int(float(r["end"]) * sample_rate))
            if s_idx < n_samples:
                f0_track[s_idx : min(e_idx, n_samples)] = 0.0

    phase_inc = 2.0 * np.pi * f0_track / sample_rate
    phase = np.cumsum(phase_inc, dtype=np.float64)
    audio = np.sin(phase).astype(np.float32)

    voiced = (f0_track > 0).astype(np.float32)
    smooth = max(8, int(0.008 * sample_rate))
    kernel = np.ones(smooth, dtype=np.float32) / float(smooth)
    envelope = np.convolve(voiced, kernel, mode="same")
    envelope = np.clip(envelope, 0.0, 1.0)
    audio *= envelope

    gain = float(10.0 ** (gain_db / 20.0))
    audio *= gain

    peak = float(np.max(np.abs(audio)))
    if peak > 0.95:
        audio *= 0.95 / peak

    stereo = np.stack([audio, audio], axis=1)
    sf.write(output_path, stereo, sample_rate)
    logger.info("Melody synth complete: %d F0 points, gain=%.1fdB, output=%s (%d samples)",
                len(values), gain_db, output_path, n_samples)
