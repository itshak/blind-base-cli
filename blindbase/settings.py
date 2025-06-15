import json
import os
from typing import Any, Dict


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
            "engine_path": "./stockfish",
            "pgn_file_directory": ".",
            "default_pgn_filename": "games.pgn",
            "games_per_page": 10,
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
            else:
                self.settings = self.default_settings.copy()
                self.save_settings()
        except (json.JSONDecodeError, IOError, TypeError, ValueError) as e:
            print(
                f"Warning: Error loading settings file '{self.settings_filename}': {e}. Using defaults."
            )
            self.settings = self.default_settings.copy()
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

__all__ = ["SettingsManager"] 