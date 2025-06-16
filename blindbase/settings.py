import json
import os
from typing import Any, Dict
import platform


class SettingsManager:
    """Manage user settings stored in a JSON file.

    The implementation is copied verbatim from the original monolith so that
    behaviour remains identical.  Future refactors may migrate this to a
    Pydantic model, but for now we keep everything as-is.
    """

    def __init__(self, settings_filename: str = "settings.json") -> None:
        self.settings_filename = settings_filename
        self.default_settings: Dict[str, Any] = {
            "lichess_moves_count": 5,
            "engine_lines_count": 3,
            "show_chessboard": True,
            "analysis_block_padding": 3,
            "engine_path": _resolve_default_engine_path(),
            "pgn_file_directory": ".",
            "default_pgn_filename": "games.pgn",
            "games_per_page": 10,
            "move_notation": "san",
        }
        self.settings: Dict[str, Any] = {}
        self.load_settings()

    # --- original implementation below -----------------------------------

    def load_settings(self) -> None:
        try:
            if os.path.exists(self.settings_filename):
                with open(self.settings_filename, "r") as f:
                    loaded_settings = json.load(f)
                    self.settings = self.default_settings.copy()
                    self.settings.update(loaded_settings)
                    for key, value in self.default_settings.items():
                        if key not in self.settings:
                            self.settings[key] = value
                        else:
                            if isinstance(value, int):
                                self.settings[key] = int(self.settings.get(key, value))
                            elif isinstance(value, bool):
                                self.settings[key] = bool(self.settings.get(key, value))
                            else:
                                self.settings[key] = str(self.settings.get(key, value))
                    # --- migration: update engine_path if user still has legacy ./stockfish ---
                    current_engine = self.settings.get("engine_path", "./stockfish")
                    resolved_default = _resolve_default_engine_path()
                    if (
                        current_engine in {"./stockfish", "stockfish"}
                        or not os.path.exists(current_engine)
                    ) and os.path.exists(resolved_default):
                        self.settings["engine_path"] = resolved_default
                        # Persist change for future runs
                        # We don't call save_settings() here to avoid recursion; defer until after load.
            else:
                self.settings = self.default_settings.copy()
                self.save_settings()
        except (json.JSONDecodeError, IOError, TypeError, ValueError) as e:
            print(
                f"Warning: Error loading settings file '{self.settings_filename}': {e}. Using defaults."
            )
            self.settings = self.default_settings.copy()
            self.save_settings()
        else:
            # ensure any migrated values are persisted
            self.save_settings()

    def save_settings(self) -> None:
        try:
            pgn_dir = self.settings.get(
                "pgn_file_directory", self.default_settings["pgn_file_directory"]
            )
            if pgn_dir == ".":
                pgn_dir = os.getcwd()
            os.makedirs(pgn_dir, exist_ok=True)
            with open(self.settings_filename, "w") as f:
                json.dump(self.settings, f, indent=4)
        except IOError as e:
            print(f"Error saving settings to '{self.settings_filename}': {e}")

    def get(self, key: str):
        return self.settings.get(key, self.default_settings.get(key))

    def set(self, key: str, value):
        if key in self.default_settings:
            default_value = self.default_settings[key]
            if isinstance(default_value, int):
                value = int(value)
            elif isinstance(default_value, bool):
                value = bool(value)
        self.settings[key] = value
        self.save_settings()

# ---------------------------------------------------------------------------
# Helper to determine packaged Stockfish binary
# ---------------------------------------------------------------------------


def _resolve_default_engine_path() -> str:
    """Return the path to the Stockfish engine bundled with the package.

    Works in three scenarios:
    1. Normal `pip install` / editable mode (package files on disk).
    2. Source tree checkout (running from repo).
    3. PyInstaller one-file executable where files are unpacked to
       ``sys._MEIPASS`` and ``sys.frozen`` is True.
    """

    import sys
    import os

    # When running under PyInstaller, non-Python data files live under _MEIPASS
    base_dir: str
    if getattr(sys, "frozen", False):  # PyInstaller sets this attr
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        engine_root = os.path.join(base_dir, "engine")
        # Binaries are collected straight into "engine/" during bundling
        system = platform.system()
        if system == "Windows":
            win_path = os.path.join(engine_root, "win", "stockfish.exe")
            return win_path if os.path.exists(win_path) else "stockfish"
        elif system == "Darwin":
            is_arm = platform.machine() in {"arm64", "aarch64"}
            filename = "stockfish" if is_arm else "stockfish_x86"
            mac_path = os.path.join(engine_root, "mac", filename)
            return mac_path if os.path.exists(mac_path) else "stockfish"
    else:
        base_dir = os.path.dirname(__file__)
        engine_root = os.path.join(base_dir, "engine")

    system = platform.system()
    if system == "Windows":
        win_path = os.path.join(engine_root, "win", "stockfish.exe")
        return win_path if os.path.exists(win_path) else "stockfish"
    elif system == "Darwin":
        is_arm = platform.machine() in {"arm64", "aarch64"}
        filename = "stockfish" if is_arm else "stockfish_x86"
        mac_path = os.path.join(engine_root, "mac", filename)
        return mac_path if os.path.exists(mac_path) else "stockfish"

    # For any other OS, just expect stockfish in PATH as ultimate fallback
    return "stockfish"

__all__ = ["SettingsManager"] 