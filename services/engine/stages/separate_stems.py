from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.services.project_store import ProjectStore
from services.engine.separation.uvr_bsroformer_adapter import separate_with_bsroformer

logger = logging.getLogger(__name__)


def run_separate_stems(
    project_id: str,
    store: ProjectStore,
    progress_cb=None,
) -> None:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])
    normalized = Path(project["artifacts"]["normalized_audio"])

    vocals = project_dir / "stems" / "vocals.wav"
    inst = project_dir / "stems" / "instrumental.wav"

    if progress_cb:
        progress_cb(project_id, "separate_stems", 10, "Loading model...")

    # Run separation in a thread so we can report progress
    separation_done = threading.Event()
    separation_error = None

    def do_separation():
        nonlocal separation_error
        try:
            logger.info(f"Starting separation for {normalized}")
            separate_with_bsroformer(normalized, vocals, inst)
            logger.info(f"Separation complete: vocals={vocals.exists()}, inst={inst.exists()}")
        except Exception as e:
            logger.error(f"Separation failed: {e}", exc_info=True)
            separation_error = e
        finally:
            separation_done.set()

    thread = threading.Thread(target=do_separation, daemon=True)
    thread.start()

    # Poll for progress
    import time
    start_time = time.time()
    while not separation_done.is_set():
        elapsed = time.time() - start_time
        # Estimate progress based on elapsed time (BS-Roformer takes 1-5 min typically)
        progress = min(90, int(elapsed / 180 * 90))  # 3 min max estimate
        if progress_cb:
            progress_cb(project_id, "separate_stems", progress, f"Separating... {elapsed:.0f}s")
        time.sleep(2)

    separation_done.wait()

    # Check for errors
    if separation_error:
        logger.error(f"Separation raised exception: {separation_error}")
        raise separation_error

    # Check if files were created
    if not vocals.exists():
        raise FileNotFoundError(f"Vocals file not created: {vocals}")
    if not inst.exists():
        raise FileNotFoundError(f"Instrumental file not created: {inst}")

    if progress_cb:
        progress_cb(project_id, "separate_stems", 100, "Stems separated")

    project["artifacts"]["vocals"] = str(vocals)
    project["artifacts"]["instrumental"] = str(inst)
    store.update_project(project_id, project)
