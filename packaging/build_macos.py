#!/usr/bin/env python3
"""Build a universal-2 (arm64 + x86_64) one-file executable of blindbase.

Usage (run on Apple Silicon macOS 11+ with Rosetta installed):
    python packaging/build_macos.py

It performs three steps:
1. Build an arm64 one-file executable with PyInstaller.
2. Build an x86_64 one-file executable under Rosetta.
3. Merge both into a single universal binary via `lipo`.

The final artefact is written to dist/blindbase (no extension).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
NAME_ARM = "blindbase_mac_arm64"
NAME_X86 = "blindbase_mac_x86_64"
FINAL_NAME = "blindbase"  # universal output

ENGINE_ARM_PATH = "blindbase/engine/mac/stockfish"
ENGINE_X86_PATH = "blindbase/engine/mac/stockfish_x86"

PYINSTALLER_COMMON_OPTS_TEMPLATE = [
    "--clean",
    "--onefile",
    "--name",
    "{name}",
    "--add-binary",
    "{engine_path}:engine",
    "blindbase/cli.py",
]

PYI_CMD_ARM = f"{sys.executable} -m PyInstaller"
# For x86 we still call under Rosetta
PYI_CMD_X86 = "arch -x86_64 $(which python3) -m PyInstaller"


def run(cmd: str, env: dict | None = None) -> None:
    print(f"\n>>> {cmd}")
    subprocess.check_call(cmd, shell=True, env=env)


def build_arm() -> None:
    opts = " ".join(PYINSTALLER_COMMON_OPTS_TEMPLATE).format(name=NAME_ARM, engine_path=ENGINE_ARM_PATH)
    run(f"{PYI_CMD_ARM} {opts}")


def build_x86() -> None:
    opts = " ".join(PYINSTALLER_COMMON_OPTS_TEMPLATE).format(name=NAME_X86, engine_path=ENGINE_X86_PATH)
    run(f"{PYI_CMD_X86} {opts}")


def main() -> None:
    os.chdir(PROJECT_ROOT)
    # Ensure dist directory is clean
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    build_arm()
    build_x86()
    print(f"Built arm64 executable at {DIST_DIR / NAME_ARM}\nBuilt x86_64 executable at {DIST_DIR / NAME_X86}")


if __name__ == "__main__":
    if sys.platform != "darwin":
        sys.exit("This script must be run on macOS.")
    main() 