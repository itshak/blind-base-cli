from __future__ import annotations

"""Pure, UI-agnostic business logic for BlindBase.

During Phase 1 we are simply re-exporting existing helpers from the old
locations so imports do not break.  In later phases the heavy logic will be
moved here for testability.
"""






# Public engine helper re-export ----------------------------------------------
# We simply expose python-chess's SimpleEngine wrapper for now.
import chess.engine as _engine

EngineProcess = _engine.SimpleEngine

# Training helpers – to be filled later. --------------------------------------
