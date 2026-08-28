from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.services.project_store import ProjectStore
from services.engine.pitch.f0_extractor import extract_f0, f0_to_notes
from services.engine.pitch.midi_writer import write_simple_midi
from services.engine.stages.utils import ffprobe_duration_seconds, write_json

logger = logging.getLogger(__name__)


def run_extract_melody(
    project_id: str,
    store: ProjectStore,
    progress_cb=None,
) -> None:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])
    vocals = Path(project["artifacts"]["vocals"])

    f0_path = project_dir / "melody" / "f0.json"
    midi_path = project_dir / "melody" / "melody.mid"

    # Skip if already exists and not explicitly forced (checking if f0 and midi are present)
    if f0_path.exists() and midi_path.exists():
        logger.info(f"Melody artifacts already exist for {project_id}, skipping extraction.")
        if progress_cb:
            progress_cb(project_id, "extract_melody", 100, "Melody already extracted (cached)")
        project["artifacts"]["f0_json"] = str(f0_path)
        project["artifacts"]["midi"] = str(midi_path)
        store.update_project(project_id, project)
        return

    if progress_cb:
        progress_cb(project_id, "extract_melody", 10, "Loading vocals stem...")

    # Extract F0 from vocals stem
    if progress_cb:
        progress_cb(project_id, "extract_melody", 20, "Running pitch detection...")

    # Run F0 extraction in a thread so we can report progress
    f0_result = {"data": None, "error": None}
    extraction_done = threading.Event()

    def do_extraction():
        try:
            f0_result["data"] = extract_f0(str(vocals))
        except Exception as e:
            f0_result["error"] = str(e)
        finally:
            extraction_done.set()

    thread = threading.Thread(target=do_extraction, daemon=True)
    thread.start()

    # Poll for progress
    start_time = time.time()
    while not extraction_done.is_set():
        elapsed = time.time() - start_time
        # F0 extraction is typically fast (10-60 seconds for a song)
        progress = min(80, int(elapsed / 60 * 70))
        if progress_cb:
            progress_cb(project_id, "extract_melody", progress, f"Extracting F0... {elapsed:.0f}s")
        time.sleep(2)

    extraction_done.wait()

    if f0_result["error"]:
        raise RuntimeError(f"F0 extraction failed: {f0_result['error']}")

    f0_data = f0_result["data"]
    logger.info("F0 extraction complete: %d frames", len(f0_data.get("values", [])))

    if progress_cb:
        progress_cb(project_id, "extract_melody", 85, "Converting F0 to notes...")

    # Convert F0 to MIDI notes
    notes = f0_to_notes(f0_data, min_note_duration=0.05)
    logger.info("F0 -> MIDI conversion: %d notes", len(notes))

    if progress_cb:
        progress_cb(project_id, "extract_melody", 90, f"Writing MIDI ({len(notes)} notes)...")

    # Write MIDI file
    midi_path = project_dir / "melody" / "melody.mid"
    if notes:
        write_simple_midi(notes, midi_path)
    else:
        # Fallback: silence MIDI if no notes detected
        write_simple_midi([], midi_path)

    # Save F0 data
    f0_path = project_dir / "melody" / "f0.json"
    write_json(f0_path, f0_data)

    if progress_cb:
        progress_cb(project_id, "extract_melody", 100, "Melody extraction complete")

    project["artifacts"]["f0_json"] = str(f0_path)
    project["artifacts"]["midi"] = str(midi_path)
    store.update_project(project_id, project)
