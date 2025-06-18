from __future__ import annotations

"""Pure, UI-agnostic business logic for BlindBase.

During Phase 1 we are simply re-exporting existing helpers from the old
locations so imports do not break.  In later phases the heavy logic will be
moved here for testability.
"""
# PGN helpers -----------------------------------------------------------------
from blindbase.storage import GameManager as _GameManager


from pathlib import Path

def load_pgn(path: str | Path):
    """Temporary thin wrapper so that callers can start importing from
    `blindbase.core.pgn` immediately.
    """
    return _GameManager(path)


# Broadcast helpers ------------------------------------------------------------
from blindbase.broadcast import BroadcastManager as _BroadcastManager, stream_game_pgn  # noqa: F401

# Engine helpers ---------------------------------------------------------------
# We simply expose python-chess's SimpleEngine wrapper for now.
import chess.engine as _engine

EngineProcess = _engine.SimpleEngine

# Training helpers – to be filled later. --------------------------------------
