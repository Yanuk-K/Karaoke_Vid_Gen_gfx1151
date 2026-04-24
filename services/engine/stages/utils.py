from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run_cmd(args: list[str]) -> None:
    subprocess.run(args, check=True)


def ffprobe_duration_seconds(audio_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return max(0.0, float(proc.stdout.strip() or 0.0))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
