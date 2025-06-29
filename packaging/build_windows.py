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

import site

PYINSTALLER_CMD_BASE = (
    f"{sys.executable} -m PyInstaller --clean --onefile --name {NAME} "
    "--add-binary blindbase/engine/win/stockfish.exe;engine/win "
    "--add-data blindbase/sounds;blindbase/sounds "
    "--hidden-import pydantic --hidden-import pydantic_settings --hidden-import tomlkit --hidden-import playsound "
)

def get_site_packages_path():
    # This will return a list of site-packages directories.
    # We assume the first one is the correct one for our environment.
    return site.getsitepackages()[0]

def build_pyinstaller_cmd():
    site_packages_path = get_site_packages_path()
    chess_path = os.path.join(site_packages_path, "chess")
    return (
        PYINSTALLER_CMD_BASE +
        f"--add-data {chess_path};chess "
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
    run(build_pyinstaller_cmd(), env=env)
    print(f"Executable created at {DIST_DIR / (NAME + '.exe')}")


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("This script must be run on Windows.")
    main() 