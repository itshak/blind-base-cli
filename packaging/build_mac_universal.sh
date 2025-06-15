#!/usr/bin/env bash
# Build a universal (arm64 + x86_64) single-file executable of BlindBase.
#
# Prerequisites:
#   1. Apple-Silicon macOS with Rosetta installed.
#   2. An Intel-only Python interpreter available (e.g. via pyenv) – set INTEL_PY.
#   3. Stockfish binaries at blindbase/engine/mac/stockfish (arm) and stockfish_x86 (x86).
#
# Usage:
#   chmod +x packaging/build_mac_universal.sh
#   ./packaging/build_mac_universal.sh
#
# Result:
#   dist/blindbase_mac_universal – fat Mach-O runnable on any Mac.
set -euo pipefail

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Configurable paths – override via env vars if needed
# ---------------------------------------------------------------------------
ARM_PY="${ARM_PY:-python3}"
INTEL_PY="${INTEL_PY:-$HOME/.pyenv/versions/3.11.9/bin/python3.11}"
VENV_ARM="venv-arm"
VENV_X86="venv-x86"
NAME_ARM="blindbase_arm_tmp"
NAME_X86="blindbase_x86_tmp"
UNIVERSAL_NAME="blindbase_mac_universal"
DIST_DIR="dist"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
function build_with() {
  local PYBIN=$1
  local VENV=$2
  local ARCH_FLAG=$3
  local ENGINE_PATH=$4
  local OUT_NAME=$5

  if [[ ! -d "$VENV" ]]; then
    echo "[+] Creating venv $VENV with $PYBIN"
    $PYBIN -m venv "$VENV"
  fi
  source "$VENV/bin/activate"
  pip install --upgrade pip >/dev/null
  pip install . pyinstaller >/dev/null
  echo "[+] Building $OUT_NAME ($ARCH_FLAG)"
  python -m PyInstaller --clean --onefile --target-arch "$ARCH_FLAG" \
         --name "$OUT_NAME" \
         --add-binary "$ENGINE_PATH:engine" \
         blindbase/cli.py
  deactivate
}

# ---------------------------------------------------------------------------
# Build arm64
# ---------------------------------------------------------------------------
build_with "$ARM_PY" "$VENV_ARM" "arm64" \
           "blindbase/engine/mac/stockfish" "$NAME_ARM"

# ---------------------------------------------------------------------------
# Build x86_64
# ---------------------------------------------------------------------------
if [[ ! -x "$INTEL_PY" ]]; then
  echo "[!] Intel Python not found/executable at $INTEL_PY" >&2
  echo "    Install one (e.g. arch -x86_64 pyenv install 3.11.9) and set INTEL_PY."
  exit 1
fi

build_with "$(echo arch -x86_64 $INTEL_PY)" "$VENV_X86" "x86_64" \
           "blindbase/engine/mac/stockfish_x86" "$NAME_X86"

# ---------------------------------------------------------------------------
# Merge with lipo
# ---------------------------------------------------------------------------
mkdir -p "$DIST_DIR"
ARM_BIN="$DIST_DIR/$NAME_ARM"
X86_BIN="$DIST_DIR/$NAME_X86"
UNIVERSAL_BIN="$DIST_DIR/$UNIVERSAL_NAME"

echo "[+] Creating universal binary via lipo"
lipo -create "$ARM_BIN" "$X86_BIN" -output "$UNIVERSAL_BIN"

# optional: strip temp files
rm -f "$ARM_BIN" "$X86_BIN"

echo "[✓] Universal binary ready: $UNIVERSAL_BIN" 