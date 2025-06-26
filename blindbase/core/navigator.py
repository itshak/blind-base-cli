"""Re-export GameNavigator in the core namespace for refactored modules."""
from __future__ import annotations

import chess.pgn

class GameNavigator:  # minimal stub for CLI help/PGN view
    """Navigate through a `chess.pgn.Game`.

    The implementation currently supports only the subset needed by the menu and
    help commands so that BlindBase can start without the legacy module. More
    advanced editing can be fleshed out later.
    """

    def __init__(self, game: chess.pgn.Game):
        self._root = game
        self._node = game  # current GameNode
        self.working_game = game
        self.has_changes = False

    # ------------------------------------------------------------------
    # Basic navigation helpers
    # ------------------------------------------------------------------
    def get_current_board(self) -> chess.Board:
        return self._node.board()

    @property
    def current_node(self):
        """Return the underlying `chess.pgn.GameNode` the navigator is on."""
        return self._node

    def make_move(self, san_or_empty: str):
        """Try to advance along SAN *san_or_empty* or main line.

        Returns (success, msg).
        """
        if san_or_empty == "":  # mainline next
            if self._node.variations:
                self._node = self._node.variations[0]
                return True, "advanced mainline"
            return False, "end of game"
        # allow numeric selection of existing variation (1-based)
        if san_or_empty.isdigit():
            idx = int(san_or_empty)
            if 1 <= idx <= len(self._node.variations):
                self._node = self._node.variations[idx - 1]
                return True, "followed variation"
            return False, "variation index out of range"

        board = self._node.board()
        try:
            move = board.parse_san(san_or_empty)
        except ValueError:
            return False, "invalid SAN"
        # try to find existing variation with that move first
        for var in self._node.variations:
            if var.move == move:
                self._node = var
                return True, "followed variation"
        # else add new variation
        child = self._node.add_variation(move)
        self._node = child
        self.has_changes = True
        return True, "added variation"

    def go_back(self) -> bool:
        """Return True if we successfully moved back a ply."""
        if self._node.parent is not None:
            self._node = self._node.parent
            return True
        return False

    def show_variations(self) -> list[str]:
        """Return a list of pretty strings describing the immediate variations."""
        lines: list[str] = []
        from blindbase.core.settings import settings
        from blindbase.utils.move_format import move_to_str
        board = self._node.board()
        for i, var in enumerate(self._node.variations, 1):
            try:
                display = move_to_str(board, var.move, settings.ui.move_notation)
            except Exception:
                display = board.san(var.move)
            lines.append(f"{i}. {display}")
        return lines

    def delete_variation(self, idx: int):
        if 1 <= idx <= len(self._node.variations):
            del self._node.variations[idx - 1]
            self.has_changes = True
            return True, "variation deleted"
        return False, "index out of range"

__all__ = ["GameNavigator"]
