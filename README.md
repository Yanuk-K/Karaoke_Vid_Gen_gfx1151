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

## Transcription Backends

The pipeline supports three transcription backends for auto-generating lyrics from audio:

| Backend | Type | Requirements | Best For |
|---------|------|--------------|----------|
| **OpenAI Whisper** | Cloud API | `OPENAI_API_KEY` | Best quality, guided by official lyrics |
| **Whisper.cpp** | Local | `WHISPER_CPP_BIN` + `WHISPER_CPP_MODEL` | Privacy-focused, offline |
| **Qwen3-ASR** | Local | GPU recommended | Multi-language (EN/JA/KO/ZH/YUE) |

### Qwen3-ASR Setup

Qwen3-ASR is already configured and ready to use. The model is downloaded locally at `models/qwen3-asr-1.7b`.

```bash
# Install the qwen-asr package (already in requirements.txt)
pip install qwen-asr

# Model path is set in .env:
# QWEN_ASR_MODEL_PATH=/home/yeunwookk/proj/Karaoke_Vid_Gen_gfx1151/models/qwen3-asr-1.7b
```

To use: select "Qwen3-ASR" in the UI and choose a language:
- **Auto-detect** - Automatic language identification
- **English** (en)
- **Japanese** (ja)
- **Korean** (ko)
- **Mandarin** (zh)
- **Cantonese** (yue)

Note: Qwen3-ASR performs best with GPU acceleration. CPU inference is possible but slow.

### Whisper.cpp Setup

```bash
export WHISPER_CPP_BIN=/path/to/whisper-cli
export WHISPER_CPP_MODEL=/path/to/ggml-model.bin
# Optional: export WHISPER_CPP_VAD_MODEL=/path/to/silero-vad.bin
```

## Optional integrations

- `UVR_REPO_PATH` defaults to `/home/yeunwookk/proj/ultimatevocalremovergui_gfx1151`.

Current BS-RoFormer adapter is wired as an integration point and uses passthrough fallback if direct model inference is unavailable.

## Core files

- API app: `services/api/app/main.py`
- Pipeline runner: `services/engine/pipeline.py`
- Stage implementations: `services/engine/stages/`
- API schema: `libs/contracts/openapi.yaml`
- Architecture docs: `docs/architecture.md`
