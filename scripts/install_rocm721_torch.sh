#!/usr/bin/env bash
set -euo pipefail

# ROCm 7.2.1 PyTorch stack for Python 3.12 (cp312)

TORCH_WHL="torch-2.9.1+rocm7.2.1.lw.gitff65f5bc-cp312-cp312-linux_x86_64.whl"
TORCHVISION_WHL="torchvision-0.24.0+rocm7.2.1.gitb919bd0c-cp312-cp312-linux_x86_64.whl"
TRITON_WHL="triton-3.5.1+rocm7.2.1.gita272dfa8-cp312-cp312-linux_x86_64.whl"
TORCHAUDIO_WHL="torchaudio-2.9.0+rocm7.2.1.gite3c6ee2b-cp312-cp312-linux_x86_64.whl"

BASE_URL="https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2.1"

python3 - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit("This ROCm wheel set requires Python 3.12 (cp312).")
PY

wget "${BASE_URL}/torch-2.9.1%2Brocm7.2.1.lw.gitff65f5bc-cp312-cp312-linux_x86_64.whl"
wget "${BASE_URL}/torchvision-0.24.0%2Brocm7.2.1.gitb919bd0c-cp312-cp312-linux_x86_64.whl"
wget "${BASE_URL}/triton-3.5.1%2Brocm7.2.1.gita272dfa8-cp312-cp312-linux_x86_64.whl"
wget "${BASE_URL}/torchaudio-2.9.0%2Brocm7.2.1.gite3c6ee2b-cp312-cp312-linux_x86_64.whl"

pip3 uninstall -y torch torchvision triton torchaudio
pip3 install \
  "${TORCH_WHL}" \
  "${TORCHVISION_WHL}" \
  "${TORCHAUDIO_WHL}" \
  "${TRITON_WHL}"
