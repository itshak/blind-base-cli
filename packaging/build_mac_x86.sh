#!/usr/bin/env bash
# Build **x86_64-only** single-file executable of BlindBase.
#
# Prerequisite: Rosetta installed. Uses GitHub's Python interpreter with Rosetta.
#
# Usage:
#   packaging/build_mac_x86.sh
#
# Result:
#   dist/blindbase_mac_x86_64  –  self-contained executable for Intel Macs.
set -euo pipefail

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Configurable paths
# ---------------------------------------------------------------------------
VENV_X86="venv-x86"
NAME_X86="blindbase_mac_x86_64"
DIST_DIR="dist"

# Check if Rosetta is installed
if ! arch -x86_64 true &>/dev/null; then
  echo "[!] Rosetta is not installed. Please install Rosetta first." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
function build_x86() {
  local PYBIN=$1
  local VENV=$2
  local OUT_NAME=$3

  if [[ ! -d "$VENV" ]]; then
    echo "[+] Creating venv $VENV with $PYBIN"
    arch -x86_64 "$PYBIN" -m venv "$VENV"
  fi
  source "$VENV/bin/activate"
  pip install --upgrade pip setuptools wheel >/dev/null
  pip install . pyinstaller pygame pyobjc >/dev/null
  echo "[+] Building $OUT_NAME (x86_64)"
  arch -x86_64 python -m PyInstaller --clean --onefile --target-arch x86_64 \
         --name "$OUT_NAME" \
         --add-binary "blindbase/engine/mac/stockfish_x86:engine/mac" \
         --add-data "blindbase/sounds:blindbase/sounds" \
         --hidden-import pydantic \
         --hidden-import pydantic_core \
         --hidden-import pydantic_settings \
         --hidden-import typing_extensions \
         --hidden-import tkinter \
         --hidden-import pygame \
         --hidden-import tomlkit \
         blindbase/menu.py
  deactivate
}

mkdir -p "$DIST_DIR"
build_x86 "$(which python3)" "$VENV_X86" "$NAME_X86"

echo "[✓] x86_64 binary ready: $DIST_DIR/$NAME_X86"
