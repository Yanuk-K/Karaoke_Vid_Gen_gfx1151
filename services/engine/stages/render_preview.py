from __future__ import annotations

import logging
from pathlib import Path

from app.services.project_store import ProjectStore
from services.engine.render.ass_builder import write_ass
from services.engine.render.melody_synth import synthesize_melody_wav
from services.engine.stages.utils import ffprobe_duration_seconds, read_json, run_cmd

logger = logging.getLogger(__name__)


def run_render_preview(
    project_id: str,
    store: ProjectStore,
    progress_cb=None,
) -> None:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])

    # Use instrumental stem (separated), fallback to normalized if separation failed
    instrumental_str = project["artifacts"].get("instrumental", "")
    normalized_str = project["artifacts"].get("normalized_audio", "")

    instrumental = Path(instrumental_str) if instrumental_str else Path()
    normalized = Path(normalized_str) if normalized_str else Path()

    if instrumental.exists() and instrumental != normalized:
        audio = instrumental
        audio_type = "instrumental"
    elif normalized.exists():
        audio = normalized
        audio_type = "normalized"
    else:
        raise FileNotFoundError("No audio found - neither instrumental nor normalized audio exists")

    duration = max(ffprobe_duration_seconds(audio), 1.0)
    logger.info("Render input: audio=%s, duration=%.1fs", audio_type, duration)

    # Load lyrics/timing
    lyrics_path = project_dir / "transcript" / "edited_lyrics.json"
    if not lyrics_path.exists():
        raise FileNotFoundError("Timing data not found - run alignment first")
    lyrics = read_json(lyrics_path)

    f0_path = project_dir / "melody" / "f0.json"
    has_melody_audio = f0_path.exists() and f0_path.stat().st_size > 10

    if progress_cb:
        progress_cb(project_id, "render_preview", 10, "Building subtitle overlay...")

    melody_ranges = lyrics.get("melody_exclusion_ranges", [])
    
    # Auto-mute gaps if enabled
    if lyrics.get("auto_mute_melody_gaps", True):
        lines = lyrics.get("lines", [])
        if lines:
            # Sort lines by start time to be safe
            sorted_lines = sorted(lines, key=lambda l: l.get("sing_start", 0))
            
            # Start gap: from 0 to first line start
            if sorted_lines[0].get("sing_start", 0) > 0.5:
                melody_ranges.append({"id": "auto_gap_start", "start": 0, "end": sorted_lines[0]["sing_start"] - 0.1})
                
            # Internal gaps
            for i in range(len(sorted_lines) - 1):
                curr_end = sorted_lines[i].get("end", 0)
                next_start = sorted_lines[i+1].get("sing_start", 0)
                if next_start - curr_end > 0.5:
                    melody_ranges.append({
                        "id": f"auto_gap_{i}",
                        "start": curr_end + 0.1,
                        "end": next_start - 0.1
                    })
            
            # End gap: from last line end to duration
            last_end = sorted_lines[-1].get("end", 0)
            if duration - last_end > 0.5:
                melody_ranges.append({"id": "auto_gap_end", "start": last_end + 0.1, "end": duration + 10})

    ass_path = project_dir / "render" / "preview.ass"
    write_ass({
        **lyrics,
        "title": project["config"].get("title", ""),
        "artist": project["config"].get("artist", ""),
        "enable_word_timing": project["config"].get("enable_word_timing", True),
    }, ass_path)
    logger.info("ASS subtitle file written: %s", ass_path)

    # Optional: Visual melody dots
    enable_visualizer = project["config"].get("enable_melody_visualizer", False)
    # Check if it's in lyrics too (from patch_timing)
    if lyrics.get("enable_melody_visualizer") is not None:
        enable_visualizer = lyrics["enable_melody_visualizer"]

    melody_ass_path = project_dir / "render" / "melody.ass"
    from services.engine.render.melody_ass_builder import write_melody_ass
    if f0_path.exists() and enable_visualizer:
        f0_data = read_json(f0_path)
        write_melody_ass(f0_data, melody_ass_path, exclusion_ranges=melody_ranges)
    elif melody_ass_path.exists():
        melody_ass_path.unlink() # Clean up if disabled

    melody_wav = project_dir / "render" / "melody_synth.wav"
    if has_melody_audio:
        f0_data = read_json(f0_path)
        gain_db = lyrics.get("melody_gain_db", -14.0)
        synthesize_melody_wav(f0_data, melody_wav, gain_db=gain_db, exclusion_ranges=melody_ranges)

    if progress_cb:
        progress_cb(project_id, "render_preview", 30, f"Rendering video ({audio_type})...")

    preview = project_dir / "render" / "preview.mp4"
    logger.info("Starting video render: %s (audio=%s)", preview.name, audio_type)
    final = project_dir / "render" / "final.mp4"

    bg_str = project["artifacts"].get("background", "")
    bg_path = Path(bg_str) if bg_str else None
    
    bg_input = []
    if bg_path and bg_path.exists():
        ext = bg_path.suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            bg_input = ["-loop", "1", "-i", str(bg_path)]
        else:
            bg_input = ["-stream_loop", "-1", "-i", str(bg_path)]
    else:
        bg_input = ["-f", "lavfi", "-i", f"color=c=0x101322:s=1280x720:r=30:d={duration}"]

    common_args = [
        "-i", str(audio),
    ]
    if has_melody_audio and melody_wav.exists():
        common_args += ["-i", str(melody_wav)]

    # Filter complex
    # [0:v] is the background
    # [1:a] is vocals/instrumental
    # [2:a] is melody synth (if exists)
    
    # Overlay hierarchy: background -> melody dots -> karaoke text
    melody_filter = f",ass={melody_ass_path}" if melody_ass_path.exists() else ""
    
    if has_melody_audio and melody_wav.exists():
        filter_complex = f"[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2{melody_filter},ass={ass_path}[v];[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
    else:
        filter_complex = f"[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2{melody_filter},ass={ass_path}[v]"

    ffmpeg_args = [
        "ffmpeg",
        "-y",
        *bg_input,
        *common_args,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "1:a" if not (has_melody_audio and melody_wav.exists()) else "[a]",
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(preview),
    ]

    import subprocess
    import threading

    render_done = threading.Event()

    def do_render():
        try:
            run_cmd(ffmpeg_args)
        finally:
            render_done.set()

    thread = threading.Thread(target=do_render, daemon=True)
    thread.start()

    # Poll for progress
    import time
    start_time = time.time()
    while not render_done.is_set():
        elapsed = time.time() - start_time
        progress = min(90, int(elapsed / max(duration, 1) * 80))
        if progress_cb:
            progress_cb(project_id, "render_preview", progress, f"Rendering... {elapsed:.0f}s")
        time.sleep(2)

    render_done.wait()

    # Copy preview to final
    run_cmd(["cp", str(preview), str(final)])

    if progress_cb:
        progress_cb(project_id, "render_preview", 100, "Video rendered")

    project["artifacts"]["preview_video"] = str(preview)
    project["artifacts"]["final_video"] = str(final)
    store.update_project(project_id, project)
