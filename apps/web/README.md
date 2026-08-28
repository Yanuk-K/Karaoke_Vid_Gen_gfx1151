# Karaoke Generator Web UI

The implemented browser frontend for the Karaoke Video Generator. It is a React + TypeScript application built with Vite, Tailwind CSS, TanStack Query, and React Router.

## Implemented workflow

- List existing projects and follow live pipeline progress.
- Upload MP3, WAV, or FLAC audio with optional reference lyrics.
- Select OpenAI Whisper, local Whisper.cpp, or local Qwen3-ASR transcription.
- Rerun the complete pipeline or restart from a selected stage.
- Replace lyrics and trigger automatic realignment.
- Edit line and word timing with inline fields, tap-to-time, locks, and millisecond nudges.
- Configure countdowns, next-line lead time, word animation, melody guides, and exclusion zones.
- Upload an image or video background.
- Preview the rendered video and download preview/final MP4, MIDI, and timing JSON artifacts.

## Development

Start the FastAPI service from the repository root first:

```bash
source .venv/bin/activate
bash scripts/run_api.sh
```

Then start Vite:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173`. During development, Vite proxies `/api/*` to `http://127.0.0.1:8000`.

## Routes

| Route | Screen |
| --- | --- |
| `/` | Project list and processing status |
| `/upload` | Audio, lyrics, ASR backend, and language selection |
| `/project/:id` | Pipeline controls, lyrics/timing editor, and video preview |

## Build

```bash
npm run build
npm run preview
```

`npm run build` runs TypeScript checking before producing the optimized Vite bundle in `dist/`.

## Source map

| Path | Purpose |
| --- | --- |
| `src/pages` | Project list, upload, and project workspace screens |
| `src/components/TimingTable.tsx` | Line/word editor, audio transport, tap timing, and melody controls |
| `src/components/VideoPreview.tsx` | MP4 preview and artifact downloads |
| `src/hooks/useProject.ts` | Query, polling, and mutation lifecycle |
| `src/lib/api.ts` | Typed API client |
| `src/types/api.ts` | Shared frontend contracts |

The end-to-end setup, screenshots, pipeline description, and benchmark are in the [root README](../../README.md).
