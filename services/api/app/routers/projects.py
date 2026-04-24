from __future__ import annotations

from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.core import config as app_config
from app.schemas.project import (
    LyricsPatchRequest,
    LyricsRead,
    ProjectCreateResponse,
    ProjectRead,
    RerunRequest,
)
from app.schemas.timing import TimingPatchRequest
from app.services.deps import get_pipeline_service, get_store
from app.services.pipeline_service import PipelineService
from app.services.project_store import ProjectStore

router = APIRouter(prefix="/projects", tags=["projects"])

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _extract_lyrics_from_transcript(payload: dict) -> str:
    segments = payload.get("segments", [])
    lines = [str(seg.get("text", "")).strip() for seg in segments if seg.get("text")]
    if lines:
        return "\n".join(lines)

    text = str(payload.get("text", "")).strip()
    if text:
        return text

    transcription = payload.get("transcription")
    if isinstance(transcription, list):
        lines = [str(item.get("text", "")).strip() for item in transcription if item.get("text")]
        return "\n".join([line for line in lines if line])

    return ""


@router.get("")
def list_projects(store: ProjectStore = Depends(get_store)) -> list[ProjectRead]:
    projects_dir = store.projects_dir
    if not projects_dir.exists():
        return []

    results = []
    for project_path in sorted(projects_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not project_path.is_dir():
            continue
        project_json = project_path / "project.json"
        if not project_json.exists():
            continue
        try:
            data = store.get_project(project_path.name)
            results.append(ProjectRead.model_validate(data))
        except Exception:
            continue

    results.sort(key=lambda p: p.created_at, reverse=True)
    return results


@router.post("", response_model=ProjectCreateResponse)
async def create_project(
    audio_file: UploadFile = File(...),
    lyrics_text: str | None = Form(None),
    transcription_backend: str = Form("openai"),
    store: ProjectStore = Depends(get_store),
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ProjectCreateResponse:
    # Validate transcription backend
    if transcription_backend not in ["openai", "whisper_cpp"]:
        transcription_backend = "openai"

    if transcription_backend == "whisper_cpp":
        whisper_errors = app_config.validate_whisper_cpp_config()
        if whisper_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Invalid whisper.cpp configuration",
                    "errors": whisper_errors,
                },
            )
    else:
        openai_errors = app_config.validate_openai_config()
        if openai_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Invalid OpenAI Whisper configuration",
                    "errors": openai_errors,
                },
            )
     
    payload = store.create_project(audio_file, lyrics_text, transcription_backend)
    pipeline.start_full_pipeline(payload["project_id"])
    return ProjectCreateResponse(project_id=payload["project_id"], status=payload["status"])


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, store: ProjectStore = Depends(get_store)) -> ProjectRead:
    try:
        return ProjectRead.model_validate(store.get_project(project_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc


@router.post("/{project_id}/rerun", response_model=ProjectCreateResponse)
def rerun_project(
    project_id: str,
    req: RerunRequest,
    store: ProjectStore = Depends(get_store),
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ProjectCreateResponse:
    _ = store.get_project(project_id)
    pipeline.rerun(project_id, req.stages, req.unlocked_only, req.transcription_backend)
    project = store.get_project(project_id)
    return ProjectCreateResponse(project_id=project_id, status=project["status"])


@router.patch("/{project_id}/lyrics", response_model=ProjectCreateResponse)
def patch_lyrics(
    project_id: str,
    req: LyricsPatchRequest,
    store: ProjectStore = Depends(get_store),
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ProjectCreateResponse:
    _ = store.get_project(project_id)
    pipeline.patch_lyrics(project_id, req.lyrics_text)
    project = store.get_project(project_id)
    return ProjectCreateResponse(project_id=project_id, status=project["status"])


@router.post("/{project_id}/lyrics/refresh", response_model=ProjectCreateResponse)
def refresh_lyrics(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ProjectCreateResponse:
    _ = store.get_project(project_id)
    pipeline.refresh_lyrics(project_id)
    project = store.get_project(project_id)
    return ProjectCreateResponse(project_id=project_id, status=project["status"])


@router.get("/{project_id}/lyrics", response_model=LyricsRead)
def get_lyrics(project_id: str, store: ProjectStore = Depends(get_store)) -> LyricsRead:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"].get("project_dir", ""))

    lyrics_path = project_dir / "input" / "lyrics.txt"
    if lyrics_path.exists():
        text = lyrics_path.read_text(encoding="utf-8").strip()
        if text:
            return LyricsRead(lyrics_text=text, source="provided")

    edited_path = project_dir / "transcript" / "edited_lyrics.json"
    if edited_path.exists():
        import json

        payload = json.loads(edited_path.read_text(encoding="utf-8"))
        lines = [str(line.get("text", "")).strip() for line in payload.get("lines", []) if line.get("text")]
        text = "\n".join(lines).strip()
        if text:
            return LyricsRead(lyrics_text=text, source="edited_lyrics")

    raw_path = project_dir / "transcript" / "raw_transcript.json"
    if raw_path.exists():
        import json

        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        text = _extract_lyrics_from_transcript(payload).strip()
        if text:
            return LyricsRead(lyrics_text=text, source="raw_transcript")

    return LyricsRead(lyrics_text="", source="empty")
    

@router.post("/{project_id}/background", response_model=ProjectCreateResponse)
async def upload_background(
    project_id: str,
    file: UploadFile = File(...),
    store: ProjectStore = Depends(get_store),
) -> ProjectCreateResponse:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])
    
    suffix = Path(file.filename or "bg.jpg").suffix
    bg_path = project_dir / "input" / f"background{suffix}"
    
    with bg_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
        
    project["artifacts"]["background"] = str(bg_path)
    store.update_project(project_id, project)
    
    return ProjectCreateResponse(project_id=project_id, status=project["status"])


@router.delete("/{project_id}/background", response_model=ProjectCreateResponse)
async def delete_background(
    project_id: str,
    store: ProjectStore = Depends(get_store),
) -> ProjectCreateResponse:
    project = store.get_project(project_id)
    if "background" in project["artifacts"]:
        del project["artifacts"]["background"]
    store.update_project(project_id, project)
    return ProjectCreateResponse(project_id=project_id, status=project["status"])


@router.patch("/{project_id}/timing", response_model=ProjectCreateResponse)
def patch_timing(
    project_id: str,
    req: TimingPatchRequest,
    store: ProjectStore = Depends(get_store),
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ProjectCreateResponse:
    _ = store.get_project(project_id)
    pipeline.patch_timing(project_id, req.model_dump())
    project = store.get_project(project_id)
    return ProjectCreateResponse(project_id=project_id, status=project["status"])


@router.get("/{project_id}/audio")
def get_audio(
    project_id: str,
    type: str = "vocals",
    store: ProjectStore = Depends(get_store),
) -> FileResponse:
    project = store.get_project(project_id)
    if type == "vocals":
        path = Path(project["artifacts"].get("vocals", ""))
    elif type == "instrumental":
        path = Path(project["artifacts"].get("instrumental", ""))
    else:
        path = Path(project.get("input_audio", ""))

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"audio {type} not ready")
    return FileResponse(path, headers=NO_STORE_HEADERS)


@router.get("/{project_id}/midi")
def get_midi(project_id: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    project = store.get_project(project_id)
    path = Path(project["artifacts"].get("midi", ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="midi not ready")
    return FileResponse(path)


@router.get("/{project_id}/video")
def get_video(
    project_id: str,
    type: str = "preview",
    store: ProjectStore = Depends(get_store),
) -> FileResponse:
    project = store.get_project(project_id)
    key = "final_video" if type == "final" else "preview_video"
    path = Path(project["artifacts"].get(key, ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="video not ready")
    return FileResponse(path, headers=NO_STORE_HEADERS)


@router.get("/{project_id}/artifacts/{name}")
def get_artifact(project_id: str, name: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    project = store.get_project(project_id)
    path = Path(project["artifacts"].get(name, ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path)


@router.get("/{project_id}/timing")
def get_timing_json(project_id: str, store: ProjectStore = Depends(get_store)) -> JSONResponse:
    """Get timing JSON for the timing editor."""
    project = store.get_project(project_id)
    path = Path(project["artifacts"].get("edited_lyrics_json", ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="timing data not available yet")
    import json
    timing = json.loads(path.read_text(encoding="utf-8"))
    return JSONResponse(content=timing)
