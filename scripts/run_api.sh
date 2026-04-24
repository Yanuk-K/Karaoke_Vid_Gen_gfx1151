#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/services/api:$ROOT_DIR"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
