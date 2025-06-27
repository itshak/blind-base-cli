#!/usr/bin/env bash
# Build **arm64-only** single-file executable of BlindBase.
#
# This is a simplified version of `build_mac_universal.sh` keeping only the
# Apple-Silicon part.  It avoids the Rosetta/x86_64 Python requirement and,
# more importantly, guarantees that the bundled wheels (pydantic-core, etc.)
# match the target architecture so we do not hit "_pydantic_core" import
# errors on M-series Macs.
#
# Usage:
#   chmod +x packaging/build_mac_arm.sh
#   ./packaging/build_mac_arm.sh
#
# Result:
#   dist/blindbase_mac_arm64  –  self-contained executable for Apple Silicon.
set -euo pipefail

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Configurable paths – override via env vars if needed
# ---------------------------------------------------------------------------
ARM_PY="${ARM_PY:-python3}"
VENV_ARM="venv-arm"
NAME_ARM="blindbase_mac_arm64"
DIST_DIR="dist"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
function build_arm() {
  local PYBIN=$1
  local VENV=$2
  local OUT_NAME=$3

  if [[ ! -d "$VENV" ]]; then
    echo "[+] Creating venv $VENV with $PYBIN"
    $PYBIN -m venv "$VENV"
  fi
  source "$VENV/bin/activate"
  pip install --upgrade pip >/dev/null
  pip install . pyinstaller >/dev/null
  echo "[+] Building $OUT_NAME (arm64)"
  python -m PyInstaller --clean --onefile --target-arch arm64 \
         --name "$OUT_NAME" \
         --add-binary "blindbase/engine/mac/stockfish:engine/mac" \
         --hidden-import pydantic \
         --hidden-import pydantic_core \
         --hidden-import pydantic_settings \
         --hidden-import typing_extensions \
         --hidden-import tomli \
         --hidden-import tomlkit \
         --runtime-hook packaging/pyi_rth_pydantic_purepython.py \
         --exclude-module pydantic_core \
         --exclude-module "pydantic_core.*" \
         --exclude-module "pydantic_core._pydantic_core" \
         blindbase/menu.py
  deactivate
}

mkdir -p "$DIST_DIR"
build_arm "$ARM_PY" "$VENV_ARM" "$NAME_ARM"

echo "[✓] ARM64 binary ready: $DIST_DIR/$NAME_ARM"
