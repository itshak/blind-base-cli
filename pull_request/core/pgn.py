"""PGN-related helpers.

This wraps `blindbase.storage.GameManager` so the rest of the application can
import from `blindbase.core.pgn` instead of touching storage directly.  When we
later migrate to a different persistence layer only this module needs to be
adjusted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import chess.pgn

class GameManager:
    """Lightweight PGN file manager (no UI).

    Handles reading a PGN file into an in-memory list of `chess.pgn.Game`
    objects and writing them back.
    """

    def __init__(self, pgn_filename: str):
        self.pgn_filename = pgn_filename
        self.games: list[chess.pgn.Game] = []
        self._load_games()

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _load_games(self) -> None:
        try:
            with open(self.pgn_filename, "r", encoding="utf-8") as fh:
                while (game := chess.pgn.read_game(fh)) is not None:
                    self.games.append(game)
        except FileNotFoundError:
            # treat missing file as empty PGN; it will be created on save
            pass

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def save_games(self) -> bool:
        """Write *all* games back to :pyattr:`pgn_filename`. Returns success."""
        try:
            with open(self.pgn_filename, "w", encoding="utf-8") as fh:
                for g in self.games:
                    exporter = chess.pgn.FileExporter(fh)
                    g.accept(exporter)
            return True
        except Exception as exc:  # pragma: no cover – only logs
            print(f"[!] Error writing PGN: {exc}")
            return False

__all__ = [
    "GameManager",
    "load_games",
    "save_games",
]


# ---------------------------------------------------------------------------
# Thin wrappers – keep public API minimal & explicit
# ---------------------------------------------------------------------------

def load_games(pgn_path: str | Path) -> GameManager:
    """Return a `GameManager` for the given PGN file (creating it if missing).
    """
    gm = GameManager(str(pgn_path))
    return gm


def save_games(game_manager: GameManager, destination: str | Path | None = None) -> None:
    """Persist the games managed by *game_manager*.

    If *destination* is None, the manager's own file path is overwritten.
    """
    dest = Path(destination) if destination else None
    if dest is None:
        game_manager.save_games()
    else:
        # when destination specified, temporarily change filename
        original = game_manager.pgn_filename
        game_manager.pgn_filename = str(dest)
        game_manager.save_games()
        game_manager.pgn_filename = original


# alias so callers can continue to write `from blindbase.core.pgn import GameManager`
GameManager = GameManager  # noqa: E305,E402
