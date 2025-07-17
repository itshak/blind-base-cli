#!/usr/bin/env python3
"""Build a Windows one-file executable of blindbase.

Run on a Windows machine (or Windows runner in CI):
    python packaging/build_windows.py

The final artefact is written to dist/blindbase.exe
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
import site
import chess

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
NAME = "blindbase"

CHESS_MODULE_PATH = Path(chess.__file__).parent

PYINSTALLER_CMD = (
    f"{sys.executable} -m PyInstaller --clean --onefile --name {NAME} "
    "--add-binary blindbase/engine/win/stockfish.exe;engine/win "
    "--add-data blindbase/sounds;blindbase/sounds "
    f"--add-data {CHESS_MODULE_PATH};chess "
    "--hidden-import pydantic --hidden-import pydantic_settings --hidden-import pygame "
    "blindbase/menu.py"
)




def run(cmd: str, env: dict | None = None) -> None:
    print(f"\n>>> {cmd}")
    subprocess.check_call(cmd, shell=True, env=env)


def main() -> None:
    os.chdir(PROJECT_ROOT)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    run(PYINSTALLER_CMD, env=env)
    print(f"Executable created at {DIST_DIR / (NAME + '.exe')}")


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("This script must be run on Windows.")
    main() 