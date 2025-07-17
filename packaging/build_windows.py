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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
NAME = "blindbase"


def run(cmd: str, env: dict | None = None) -> None:
    print(f"\n>>> {cmd}")
    subprocess.check_call(cmd, shell=True, env=env)


def main() -> None:
    os.chdir(PROJECT_ROOT)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)

    # Dynamically determine the path to the 'chess' module
    pip_show_output = subprocess.run(
        [sys.executable, "-m", "pip", "show", "python-chess"],
        capture_output=True, text=True, check=True
    ).stdout
    for line in pip_show_output.splitlines():
        if line.startswith("Location:"):
            chess_location = Path(line.split(": ", 1)[1])
            CHESS_MODULE_PATH = chess_location / "chess"
            break
    else:
        raise RuntimeError("Could not find 'chess' module location.")

    PYINSTALLER_CMD = (
        f"{sys.executable} -m PyInstaller --clean --onefile --name {NAME} "
        "--add-binary blindbase/engine/win/stockfish.exe;engine/win "
        "--add-data blindbase/sounds;blindbase/sounds "
        f"--add-data {CHESS_MODULE_PATH};chess "
        "--hidden-import pydantic --hidden-import pydantic_settings --hidden-import pygame "
        "blindbase/menu.py"
    )

    run(PYINSTALLER_CMD, env=env)

    print(f"Executable created at {DIST_DIR / (NAME + '.exe')}")


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("This script must be run on Windows.")
    main() 