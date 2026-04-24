# Karaoke Video Generator (Local-First MVP)

Local pipeline to turn one song into a karaoke preview/final video with editable timing artifacts.

## What is implemented

- FastAPI local API for project lifecycle.
- Sequential stage runner (no Redis/Celery/DB).
- Filesystem project storage under `data/projects/{project_id}`.
- Stage chain: normalize -> separate -> lyrics -> align -> midi -> render.
- Timing JSON contract with `display_start` and `sing_start`.
- Edit-only rerender path via `PATCH /projects/{id}/timing`.

## Running the Application

### 1. Start Backend (API)

The backend handles audio processing, lyric alignment, and video generation.

```bash
# Activate venv if not already active
source .venv/bin/activate

# Start the FastAPI server
bash scripts/run_api.sh
```

- **Swagger Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/health`

### 2. Start Frontend (Web UI)

The frontend provides a user-friendly interface for managing projects and editing timings.

```bash
cd apps/web
npm install
npm run dev
```

- **Web App**: `http://localhost:5173` (or as shown in terminal)
- **Note**: Ensure the Backend is running for the Web UI to function correctly.

## Optional integrations

- Set `WHISPER_CPP_BIN` and `WHISPER_CPP_MODEL` to enable local whisper.cpp transcription.
- `UVR_REPO_PATH` defaults to `/home/yeunwookk/proj/ultimatevocalremovergui_gfx1151`.

Current BS-RoFormer adapter is wired as an integration point and uses passthrough fallback if direct model inference is unavailable.

## Core files

- API app: `services/api/app/main.py`
- Pipeline runner: `services/engine/pipeline.py`
- Stage implementations: `services/engine/stages/`
- API schema: `libs/contracts/openapi.yaml`
- Architecture docs: `docs/architecture.md`
