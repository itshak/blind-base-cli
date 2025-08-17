"""Application settings management using Pydantic + TOML.

The settings are stored in ``~/.config/blindbase.toml`` and can be overridden
by environment variables prefixed with ``BB_``.

Backward-compatibility: if an older ``~/.blindbase.json`` file is found it is
imported once then renamed to ``.blindbase.json.bak`` to avoid overriding the
TOML file on subsequent runs.
"""
from __future__ import annotations

import json
import os
import shutil

from pathlib import Path
from typing import Any, Dict

import typer
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from tomlkit import dumps, parse, TOMLDocument

APP_DIR = Path(typer.get_app_dir("blindbase"))
CONFIG_PATH = APP_DIR / "blindbase.toml"
OLD_JSON_PATH = Path.home() / ".blindbase.json"  # keep legacy path for migration


class EngineSettings(BaseSettings):
    lines: int = Field(3, description="Number of PV lines to show")
    path: str | None = Field(None, description="Override path to Stockfish executable")
    eval_depth: int = Field(30, description="Evaluation depth for move candidates")

    # Use a dedicated env_prefix so that the OS PATH environment variable
    # does not inadvertently populate the `path` field.
    model_config = SettingsConfigDict(extra="ignore", env_prefix="BB_ENGINE_")


class OpeningTreeSettings(BaseSettings):
    lichess_moves: int = Field(5, description="How many moves to request/display per branch from Lichess API")
    cache_hours: int = Field(24, description="How long to cache opening tree results")

    model_config = SettingsConfigDict(extra="ignore")


from typing import Literal

class UISettings(BaseSettings):
    theme: str = Field("light", description="colour theme (light|dark)")
    show_board: bool = Field(True, description="Display ASCII board; if False only text")
    games_per_page: int = Field(10, description="Pagination size for games list")
    move_notation: Literal["san", "uci", "nato", "anna"] = Field("san", description="Move notation style")
    board_theme: str = Field("default", description="Board theme (default, high_contrast_light, high_contrast_dark, colorblind_red_green)")

    model_config = SettingsConfigDict(extra="ignore")





class BroadcastSettings(BaseSettings):
    tournaments_limit: int = Field(10, description="Number of tournaments to fetch from Lichess API")

    model_config = SettingsConfigDict(extra="ignore")


class OpeningTrainingSettings(BaseSettings):
    number_of_attempts: int = Field(3, description="Attempts allowed to guess each move")

    model_config = SettingsConfigDict(extra="ignore")


class PGNSettings(BaseSettings):
    directory: Path = Field(Path("."), description="Default PGN files directory")

    model_config = SettingsConfigDict(extra="ignore")


class Settings(BaseSettings):
    """Top-level settings object."""

    engine: EngineSettings = Field(default_factory=EngineSettings)
    opening_tree: OpeningTreeSettings = Field(default_factory=OpeningTreeSettings)
    ui: UISettings = Field(default_factory=UISettings)
    opening_training: OpeningTrainingSettings = Field(default_factory=OpeningTrainingSettings)
    broadcasts: BroadcastSettings = Field(default_factory=BroadcastSettings)
    pgn: PGNSettings = Field(default_factory=PGNSettings)

    model_config = SettingsConfigDict(env_prefix="BB_", extra="ignore")

    # ---------------------------------------------------------------------
    # Persistence helpers
    # ---------------------------------------------------------------------

    @classmethod
    def _load_toml(cls) -> Dict[str, Any]:
        if CONFIG_PATH.exists():
            return parse(CONFIG_PATH.read_text())  # type: ignore[arg-type]
        return {}

    @classmethod
    def _migrate_json(cls) -> Dict[str, Any]:
        """If legacy JSON exists, convert it and rename the old file."""
        if not OLD_JSON_PATH.exists():
            return {}
        data = json.loads(OLD_JSON_PATH.read_text())
        # Map old flat keys to new nested ones (best-effort)
        mapped: Dict[str, Any] = {}
        if "engine_lines" in data:
            mapped.setdefault("engine", {})["lines"] = int(data["engine_lines"])
        if "lichess_moves" in data:
            mapped.setdefault("opening_tree", {})["lichess_moves"] = int(data["lichess_moves"])
        if "show_board" in data:
            mapped.setdefault("ui", {})["show_board"] = bool(data["show_board"])
        if "games_per_page" in data:
            mapped.setdefault("ui", {})["games_per_page"] = int(data["games_per_page"])
        if "move_notation" in data:
            mapped.setdefault("ui", {})["move_notation"] = str(data["move_notation"])
        if "pgn_dir" in data:
            mapped.setdefault("pgn", {})["directory"] = str(data["pgn_dir"])
        if "cache_hours" in data:
            mapped.setdefault("opening", {})["cache_hours"] = int(data["cache_hours"])
        if "ui_theme" in data:
            mapped.setdefault("ui", {})["theme"] = str(data["ui_theme"])
        # backup old file
        OLD_JSON_PATH.rename(OLD_JSON_PATH.with_suffix(".bak"))
        return mapped

    @classmethod
    def load(cls) -> "Settings":
        raw = cls._load_toml()
        if not raw:
            # first run, try json migration
            raw = cls._migrate_json()
        inst = cls(**raw)
        # ------------------------------------------------------------------
        # Post-processing for engine.path
        # ------------------------------------------------------------------
        # In some previous versions a bug saved the full $PATH string into
        # engine.path.  Detect such cases (the value equals the current PATH or
        # contains multiple path-separator entries) and reset to *None* so that
        # the built-in Stockfish bundled with BlindBase is used by default.
        if inst.engine.path:
            is_accidentally_path_env = inst.engine.path == os.environ.get("PATH") or os.pathsep in inst.engine.path
            if is_accidentally_path_env:
                inst.engine.path = None

        # If the user explicitly configured a custom Stockfish executable path
        # make it available to the Engine helper through the environment.  We
        # expand a leading '~' so both GUI and subprocesses resolve the same
        # absolute file location.
        if inst.engine.path:
            os.environ["STOCKFISH_EXECUTABLE"] = str(Path(inst.engine.path).expanduser())

        return inst

    # ------------------------------------------------------------------
    # save
    # ------------------------------------------------------------------
    def save(self) -> None:
        # round-trip preserve comments if toml exists
        if CONFIG_PATH.exists():
            doc: TOMLDocument = parse(CONFIG_PATH.read_text())  # type: ignore[arg-type]
        else:
            doc = TOMLDocument()

        # update values
        def _assign(section: str, values: Dict[str, Any]):
            # reset section to remove stale keys
            doc[section] = TOMLDocument()
            for k, v in values.items():
                if isinstance(v, Path):
                    doc[section][k] = str(v)
                else:
                    doc[section][k] = v

        _assign("engine", self.engine.model_dump(exclude_none=True))
        _assign("opening_tree", self.opening_tree.model_dump(exclude_none=True))
        _assign("ui", self.ui.model_dump(exclude_none=True))
        _assign("opening_training", self.opening_training.model_dump(exclude_none=True))
        _assign("broadcasts", self.broadcasts.model_dump(exclude_none=True))
        _assign("pgn", self.pgn.model_dump(exclude_none=True))

        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(dumps(doc))
        except (IOError, PermissionError):
            # Silently ignore errors saving settings, e.g. in a read-only env
            pass


# singleton instance
settings = Settings.load()

__all__ = ["Settings", "settings"]