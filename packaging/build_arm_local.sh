#!/usr/bin/env bash
# Build BlindBase single-file executable for Apple-Silicon macOS
#
# Usage:
#   ./packaging/build_arm_local.sh
#
# The script creates (or reuses) a local virtual-environment, installs
# BlindBase plus PyInstaller, and produces `dist/blindbase_mac_arm64`.
set -euo pipefail

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

VENV_DIR="venv-build-arm"
PY_VERSION=${PY_VERSION:-"python3"}  # allow override

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[+] Creating virtual-env $VENV_DIR"
  $PY_VERSION -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "[+] Installing dependencies into venv"
pip install --upgrade pip >/dev/null
pip install . pyinstaller >/dev/null

echo "[+] Building executable (arm64)"
python -m PyInstaller \
        --clean --onefile --target-arch arm64 \
        --name blindbase_mac_arm64 \
        --add-binary blindbase/engine/mac/stockfish:engine \
        blindbase/cli.py

echo "[✓] Built dist/blindbase_mac_arm64" 