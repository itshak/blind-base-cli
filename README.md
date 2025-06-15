# BlindBase – Accessible Chess-Study CLI

BlindBase is a text-mode chess study tool that brings Stockfish analysis, Lichess Masters statistics and speech feedback to the terminal. It is designed for visually-impaired players but equally useful for anyone who prefers a distraction-free CLI over a GUI.

## Features

- Interactive board with Rich ASCII graphics or screen-reader-friendly layout.
- Fast Stockfish analysis (multi-PV).
- Masters moves tree (lichess.org database).
- PGN navigation, variation editing, comments.
- Broadcast streaming of live games.
- Speech synthesis (optional) via `pyttsx3`.
- Ships with Stockfish binaries for macOS (arm64 + x86_64) and Windows x64 – no separate download required.
- Stand-alone executables ship with Stockfish (macOS arm64/x86_64 and Windows x64) — no separate download required, while the PyPI wheel stays slim and expects Stockfish in your PATH.

## Quick start

```bash
pip install blindbase           # installs lightweight wheel (Stockfish required, see below)

blindbase play games.pgn        # open PGN browser
```

Command list appears below the board; type `a`

## Quick start (continued)

Command list appears below the board; type `a` to start engine analysis, `t` to view Masters moves, `m` to save.

### Install Stockfish (required for pip users)

The PyPI wheel is lightweight and **does not include** the Stockfish engine. Install Stockfish once and make sure it is discoverable from the shell:

• **macOS** – `brew install stockfish`

• **Windows** – download `stockfish_15_x64_avx2.exe` (or the `..._noavx2.exe` if your CPU lacks AVX2) from the [official site](https://stockfishchess.org/download/) and place it somewhere in your `%PATH%` (e.g. `C:\Windows\System32`).

• **Linux** – `sudo apt install stockfish` or your distro's package.

Alternatively, pass an explicit path:

```bash
blindbase play games.pgn --engine /full/path/to/stockfish
```

The single-file executables (`blindbase_mac_arm64`, `blindbase.exe`, …) already contain the correct engine and do **not** need this step.

## Building from source

```bash
git clone https://github.com/itshak/blind-base-cli.git
cd blind-base-cli
pip install -e .[dev]          # editable install with dev extras
```

Run unit tests:

```bash
pytest -q
```

## Single-file executables

The repo provides scripts and CI workflow to create stand-alone binaries (no Python required).

### Local Apple-Silicon build

```bash
python3 -m venv venv
source venv/bin/activate
pip install . pyinstaller
python -m PyInstaller \
    --clean --onefile --target-arch arm64 \
    --name blindbase_mac_arm64 \
    --add-binary blindbase/engine/mac/stockfish:engine \
    blindbase/cli.py
```

`dist/blindbase_mac_arm64` runs on Apple-Silicon and Intel Macs (via Rosetta).

### CI builds (Intel macOS & Windows)

GitHub Actions workflow [`release.yml`](.github/workflows/release.yml) publishes artefacts on every push tag:

- `blindbase_mac_x86_64` – native Intel Mac binary
- `blindbase.exe` – Windows 64-bit binary

Download them from the **Actions → run → Artefacts** section.

## Package layout

```
blindbase/
 ├─ cli.py               # classic interactive UI
 ├─ app.py               # Typer entry-point
 ├─ engine/              # bundled Stockfish binaries (for PyInstaller builds)
 │   ├─ mac/stockfish          (arm64)
 │   ├─ mac/stockfish_x86      (x86_64)
 │   └─ win/stockfish.exe      (win64)
 └─ ...
packaging/
 ├─ build_macos.py       # PyInstaller helper script
 └─ build_windows.py
```

## Contributing

Pull requests are welcome! Please open an issue first to discuss major changes.

1. Fork → feature branch → PR.
2. Run `pre-commit run --all-files` before pushing.
3. Ensure `pytest` and `ruff` pass.

## License

BlindBase is licensed under the MIT License. Stockfish binaries are GPLv3; they are distributed unmodified in the `engine/` directory – see `engine/LICENSE`. By using the one-file executables you accept the terms of Stockfish's GPL.

- CI builds produce single-file executables for macOS (arm64 + x86_64) and Windows x64.
