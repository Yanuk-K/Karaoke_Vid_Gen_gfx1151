from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _fmt_ts(seconds: float) -> str:
    s = max(0.0, seconds)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def _pitch_to_y(pitch: float, y_top: int = 360, y_bottom: int = 700) -> int:
    lo, hi = 36.0, 84.0
    clamped = min(max(pitch, lo), hi)
    ratio = (clamped - lo) / (hi - lo)
    return int(y_bottom - ratio * (y_bottom - y_top))


def _hz_to_midi(hz: float) -> float:
    if hz <= 0:
        return 0.0
    import math

    return 69.0 + 12.0 * math.log2(hz / 440.0)


def write_melody_ass(f0_data: dict, ass_path: Path, exclusion_ranges: list[dict] | None = None) -> None:
    """Build a simple moving-note overlay from f0 data."""
    header = """[Script Info]
Title: Melody Overlay
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Melody,Noto Sans CJK KR,26,&H0063D8FF,&H0063D8FF,&H00101010,&H00000000,1,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1
Style: MelodyGuide,Noto Sans CJK KR,22,&H004B4B4B,&H004B4B4B,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    values = f0_data.get("values", [])
    if not values:
        ass_path.write_text(header, encoding="utf-8")
        return

    events: list[str] = []
    # Horizontal guide lines
    for midi_note in (48, 60, 72):
        y = _pitch_to_y(float(midi_note))
        events.append(
            "Dialogue: 0,0:00:00.00,9:59:59.99,MelodyGuide,,0,0,0,,"
            f"{{\\pos(640,{y})\\alpha&H90&}}────────────────────────────────────────"
        )

    frame_stride = 2
    trail = 1.2
    for idx in range(0, len(values), frame_stride):
        item = values[idx]
        if not item.get("voiced"):
            continue
        hz = float(item.get("f0_hz", 0.0))
        if hz <= 0:
            continue

        t = float(item.get("time", 0.0))
        
        # Check exclusion
        excluded = False
        if exclusion_ranges:
            for r in exclusion_ranges:
                if float(r["start"]) <= t <= float(r["end"]):
                    excluded = True
                    break
        if excluded:
            continue
        midi = _hz_to_midi(hz)
        y = _pitch_to_y(midi)
        x = 980
        end = t + trail
        events.append(
            "Dialogue: 2,"
            f"{_fmt_ts(t)},{_fmt_ts(end)},Melody,,0,0,0,,"
            f"{{\\move({x},{y},{x - 520},{y})}}●"
        )

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    melody_events = len([e for e in events if "Dialogue:" in e and "MelodyGuide" not in e])
    logger.info("Melody ASS written: %d F0 points, %d melody events, %d exclusion ranges",
                len(values), melody_events, len(exclusion_ranges) if exclusion_ranges else 0)
