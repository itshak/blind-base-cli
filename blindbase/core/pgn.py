"""PGN-related helpers.

This wraps `blindbase.storage.GameManager` so the rest of the application can
import from `blindbase.core.pgn` instead of touching storage directly.  When we
later migrate to a different persistence layer only this module needs to be
adjusted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from blindbase.storage import GameManager

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
