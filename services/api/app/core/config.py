from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# Load .env file from project root
ROOT_DIR = Path(__file__).resolve().parents[4]
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)

DATA_DIR = ROOT_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"

UVR_REPO_PATH = Path(
    os.getenv("UVR_REPO_PATH", "/home/yeunwookk/proj/ultimatevocalremovergui_gfx1151")
)
UVR_BSROFORMER_CKPT = Path(
    os.getenv(
        "UVR_BSROFORMER_CKPT",
        str(UVR_REPO_PATH / "models" / "MDX_Net_Models" / "model_bs_roformer_ep_317_sdr_12.9755.ckpt"),
    )
)
UVR_BSROFORMER_YAML = Path(
    os.getenv(
        "UVR_BSROFORMER_YAML",
        str(UVR_REPO_PATH / "models" / "MDX_Net_Models" / "model_data" / "mdx_c_configs" / "model_bs_roformer_ep_317_sdr_12.9755.yaml"),
    )
)
BSROFORMER_SPEED_PRESET = os.getenv("BSROFORMER_SPEED_PRESET", "balanced").strip().lower()

WHISPER_CPP_BIN = os.getenv("WHISPER_CPP_BIN", "")
WHISPER_CPP_MODEL = os.getenv("WHISPER_CPP_MODEL", "")
WHISPER_CPP_VAD_MODEL = os.getenv("WHISPER_CPP_VAD_MODEL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", None)
QWEN_ASR_MODEL_PATH = os.getenv("QWEN_ASR_MODEL_PATH", "")
QWEN_ASR_FORCED_ALIGNER_PATH = os.getenv("QWEN_ASR_FORCED_ALIGNER_PATH", "")

DEFAULT_NEXT_LINE_LEAD_TIME = 0.9
DEFAULT_COUNTDOWN_OFFSET = 2.0


def validate_whisper_cpp_config() -> list[str]:
    errors: list[str] = []
    if not WHISPER_CPP_BIN:
        errors.append("WHISPER_CPP_BIN is not set")
    else:
        bin_path = Path(WHISPER_CPP_BIN)
        if not bin_path.is_file():
            errors.append(
                f"WHISPER_CPP_BIN must point to executable file, got: {WHISPER_CPP_BIN}"
            )

    if not WHISPER_CPP_MODEL:
        errors.append("WHISPER_CPP_MODEL is not set")
    else:
        model_path = Path(WHISPER_CPP_MODEL)
        if not model_path.is_file():
            errors.append(
                f"WHISPER_CPP_MODEL must point to model file, got: {WHISPER_CPP_MODEL}"
            )

    if WHISPER_CPP_VAD_MODEL:
        vad_path = Path(WHISPER_CPP_VAD_MODEL)
        if not vad_path.is_file():
            errors.append(
                f"WHISPER_CPP_VAD_MODEL must point to model file, got: {WHISPER_CPP_VAD_MODEL}"
            )
    return errors


def validate_openai_config() -> list[str]:
    errors: list[str] = []
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is not set")
    return errors


def validate_qwen_asr_config() -> list[str]:
    errors: list[str] = []
    if QWEN_ASR_MODEL_PATH:
        model_path = Path(QWEN_ASR_MODEL_PATH)
        if not model_path.exists():
            errors.append(
                f"QWEN_ASR_MODEL_PATH must point to a valid model directory or file, got: {QWEN_ASR_MODEL_PATH}"
            )
    if QWEN_ASR_FORCED_ALIGNER_PATH:
        aligner_path = Path(QWEN_ASR_FORCED_ALIGNER_PATH)
        if not aligner_path.exists():
            errors.append(
                f"QWEN_ASR_FORCED_ALIGNER_PATH must point to a valid model directory or file, got: {QWEN_ASR_FORCED_ALIGNER_PATH}"
            )
    return errors
