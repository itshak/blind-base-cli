#!/usr/bin/env bash
# Build **x86_64-only** single-file executable of BlindBase.
#
# Prerequisite: Rosetta installed and an Intel Python interpreter available. If
# you use pyenv, install one via:
#   arch -x86_64 pyenv install 3.11.9
# and then set INTEL_PY accordingly.
#
# Usage:
#   INTEL_PY=$HOME/.pyenv/versions/3.11.9/bin/python3.11 \
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
INTEL_PY="${INTEL_PY:-$HOME/.pyenv/versions/3.11.9/bin/python3.11}"
VENV_X86="venv-x86"
NAME_X86="blindbase_mac_x86_64"
DIST_DIR="dist"

if [[ ! -x "$INTEL_PY" ]]; then
  echo "[!] Intel Python not found/executable at $INTEL_PY" >&2
  echo "    Install one (e.g. arch -x86_64 pyenv install 3.11.9) and set INTEL_PY." >&2
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
  pip install --upgrade pip >/dev/null
  pip install . pyinstaller >/dev/null
  echo "[+] Building $OUT_NAME (x86_64)"
  arch -x86_64 python -m PyInstaller --clean --onefile --target-arch x86_64 \
         --name "$OUT_NAME" \
         --add-binary "blindbase/engine/mac/stockfish_x86:engine/mac" \
         blindbase/menu.py
  deactivate
}

mkdir -p "$DIST_DIR"
build_x86 "$INTEL_PY" "$VENV_X86" "$NAME_X86"

echo "[✓] x86_64 binary ready: $DIST_DIR/$NAME_X86"
