from __future__ import annotations

import os
import shutil
import sys
import gc
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn as nn

from app.core import config


def _build_preset_attempts(selected: str) -> list[dict]:
    presets = {
        "fast": {"chunk_seconds": 2.0, "overlap": 2, "batch": 2, "cleanup_every": 6},
        "balanced": {"chunk_seconds": 1.6, "overlap": 2, "batch": 1, "cleanup_every": 3},
        "quality": {"chunk_seconds": 1.0, "overlap": 4, "batch": 1, "cleanup_every": 1},
        "safe": {"chunk_seconds": 0.8, "overlap": 4, "batch": 1, "cleanup_every": 1},
    }
    selected = selected if selected in presets else "balanced"
    if selected == "fast":
        return [presets["fast"], presets["balanced"], presets["safe"]]
    if selected == "balanced":
        return [presets["balanced"], presets["safe"]]
    if selected == "quality":
        return [presets["quality"], presets["safe"]]
    return [presets["safe"]]


def separate_with_bsroformer(
    input_wav: Path,
    vocals_out: Path,
    instrumental_out: Path,
) -> None:
    """Run BS-RoFormer separation using the UVR model files.

    Uses UVR's proven demix implementation pattern with batching and
    proper overlap-add windowing to avoid ROCm memory fragmentation.
    """
    # Enable expandable segments for ROCm memory fragmentation fix
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    ckpt_path = config.UVR_BSROFORMER_CKPT
    yaml_path = config.UVR_BSROFORMER_YAML
    uvr_repo = config.UVR_REPO_PATH

    if not (ckpt_path.exists() and yaml_path.exists() and uvr_repo.exists()):
        _passthrough_separation(input_wav, vocals_out, instrumental_out)
        return

    uvr_lib_path = uvr_repo / "lib_v5"
    if str(uvr_repo) not in sys.path:
        sys.path.insert(0, str(uvr_repo))
    if str(uvr_lib_path) not in sys.path:
        sys.path.insert(0, str(uvr_lib_path))

    try:
        import yaml
        from lib_v5.bs_roformer import BSRoformer
    except ImportError:
        print(f"ImportError: Could not import BSRoformer from lib_v5.bs_roformer")
        _passthrough_separation(input_wav, vocals_out, instrumental_out)
        return

    with open(yaml_path, "r") as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)

    model_kwargs = cfg["model"]
    model = BSRoformer(**model_kwargs)

    state_dict = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    if "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    model.load_state_dict(state_dict, strict=False)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()

    # sf.read returns (samples, channels), but UVR code expects (channels, samples)
    audio, sr = sf.read(input_wav, dtype="float32")
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=0)
    else:
        audio = audio.T

    # Convert entire mix to tensor on CPU first (UVR pattern)
    mix = torch.tensor(audio, dtype=torch.float32)

    # Inference parameters from YAML config
    inference_cfg = cfg.get("inference", {})
    dim_t = inference_cfg.get("dim_t", 801)
    default_overlap = int(inference_cfg.get("num_overlap", 4))
    default_batch = int(inference_cfg.get("batch_size", 1))

    hop_length = cfg["audio"]["hop_length"]
    yaml_chunk = hop_length * (dim_t - 1)

    target_instrument = cfg["training"].get("target_instrument")
    S = 1 if target_instrument else len(cfg["training"]["instruments"])

    selected_preset = getattr(config, "BSROFORMER_SPEED_PRESET", "balanced")
    attempts = _build_preset_attempts(selected_preset)

    estimated_sources = None
    last_error: Exception | None = None

    for preset in attempts:
        try:
            chunk_size = min(yaml_chunk, int(preset["chunk_seconds"] * sr))
            overlap = max(2, int(preset["overlap"]))
            batch_size = max(1, max(int(preset["batch"]), default_batch if default_batch > 0 else 1))
            cleanup_every = max(1, int(preset["cleanup_every"]))

            if chunk_size <= 0:
                chunk_size = min(yaml_chunk, int(1.0 * sr))
            step = max(1, int(chunk_size / overlap))
            fade_size = max(1, chunk_size // 10)

            local_mix = mix
            length_init = local_mix.shape[-1]
            if length_init > 2 * (chunk_size - step) and (chunk_size - step > 0):
                local_mix = nn.functional.pad(local_mix, (chunk_size - step, chunk_size - step), mode="reflect")

            fadein = torch.linspace(0, 1, fade_size).to(device)
            fadeout = torch.linspace(1, 0, fade_size).to(device)
            window_start = torch.ones(chunk_size, device=device)
            window_middle = torch.ones(chunk_size, device=device)
            window_finish = torch.ones(chunk_size, device=device)
            window_start[-fade_size:] *= fadeout
            window_finish[:fade_size] *= fadein
            window_middle[:fade_size] *= fadein
            window_middle[-fade_size:] *= fadeout

            batch_data = []
            batch_locations = []
            i = 0
            flush_count = 0

            with torch.inference_mode():
                req_shape = (S,) + tuple(local_mix.shape)
                result = torch.zeros(req_shape, dtype=torch.float32, device=device)
                counter = torch.zeros(req_shape, dtype=torch.float32, device=device)

                while i < local_mix.shape[1]:
                    part = local_mix[:, i : i + chunk_size].to(device)
                    length = part.shape[-1]

                    if length < chunk_size:
                        if length > chunk_size // 2 + 1:
                            part = nn.functional.pad(part, (0, chunk_size - length), mode="reflect")
                        else:
                            part = nn.functional.pad(part, (0, chunk_size - length, 0, 0), mode="constant", value=0)

                    batch_data.append(part)
                    batch_locations.append((i, length))
                    i += step

                    if len(batch_data) >= batch_size or i >= local_mix.shape[1]:
                        arr = torch.stack(batch_data, dim=0)
                        x = model(arr)

                        for j, (start, length) in enumerate(batch_locations):
                            window = window_middle
                            if start == 0:
                                window = window_start
                            elif i >= local_mix.shape[1]:
                                window = window_finish

                            max_result_len = result.shape[-1] - start
                            max_model_len = x[j].shape[-1]
                            max_window_len = window.shape[-1]
                            valid_length = min(length, max_result_len, max_model_len, max_window_len)

                            if valid_length <= 0:
                                continue

                            result[..., start : start + valid_length] += x[j][..., :valid_length] * window[
                                ..., :valid_length
                            ]
                            counter[..., start : start + valid_length] += window[..., :valid_length]

                        batch_data = []
                        batch_locations = []
                        flush_count += 1

                        del arr, x
                        if flush_count % cleanup_every == 0:
                            gc.collect()
                            if device == "cuda":
                                torch.cuda.empty_cache()

                estimated_sources = result / counter.clamp(min=1e-10)

                if length_init > 2 * (chunk_size - step) and (chunk_size - step > 0):
                    estimated_sources = estimated_sources[..., (chunk_size - step) : -(chunk_size - step)]

            break
        except torch.OutOfMemoryError as exc:
            last_error = exc
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()
            continue

    if estimated_sources is None:
        if last_error is not None:
            raise last_error
        raise RuntimeError("BS-RoFormer separation failed with unknown error")

    # Extract vocals/instrumental
    if target_instrument:
        vocals = estimated_sources[0].cpu().numpy()
        vocals = vocals[:, :audio.shape[1]]
        instrumental = audio[:, : vocals.shape[1]] - vocals
    else:
        instruments = cfg["training"]["instruments"]
        vocals_idx = instruments.index("vocals") if "vocals" in instruments else 0
        vocals = estimated_sources[vocals_idx].cpu().numpy()
        mask = np.ones(len(instruments), dtype=bool)
        mask[vocals_idx] = False
        instrumental = estimated_sources[mask].sum(axis=0).cpu().numpy()

    sf.write(vocals_out, vocals.T, sr)
    sf.write(instrumental_out, instrumental.T, sr)


def _passthrough_separation(
    input_wav: Path,
    vocals_out: Path,
    instrumental_out: Path,
) -> None:
    """Fallback: copy input as both stems so pipeline can continue."""
    shutil.copy2(input_wav, vocals_out)
    shutil.copy2(input_wav, instrumental_out)
