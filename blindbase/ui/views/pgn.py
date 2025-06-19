"""PGN viewer `View` implementation."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import chess
import chess.pgn
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from blindbase.ui.base import View
from blindbase.core.settings import settings
from blindbase.utils.move_format import move_to_str
from blindbase.ui.board import render_board

__all__ = ["PgnView"]


class PgnView(View):
    """Simple read-only display of a single PGN game."""

    def __init__(self, game: chess.pgn.Game, *, ply: int = 0, flipped: bool = False):
        self._game = game
        self._flipped = flipped
        self._ply = ply

    # ------------------------------------------------------------------
    # View hooks
    # ------------------------------------------------------------------

    def header(self) -> RenderableType:  # noqa: D401
        hdr = self._game.headers
        title = hdr.get("Event", "PGN Game")
        white = hdr.get("White", "?")
        black = hdr.get("Black", "?")
        return Text(f"{title} – {white} vs {black}", style="bold")

    def body(self) -> RenderableType:  # noqa: D401
        # ------------------------------------------------------------------
        # Apply moves up to current ply and build context -------------------
        # ------------------------------------------------------------------
        board = self._game.board()
        node = self._game  # root
        last_move_text = "Initial position"
        for idx in range(self._ply):
            next_node = node.variations[0]
            san = move_to_str(board, next_node.move, settings.ui.move_notation)
            move_no = idx // 2 + 1
            prefix = f"{move_no}{'.' if idx % 2 == 0 else '...'}"
            last_move_text = f"{prefix} {san}"
            board.push(next_node.move)
            node = next_node

        # Determine whose turn
        turn_str = "White" if board.turn else "Black"

        # Collect next moves (variations)
        next_moves: list[str] = []
        for v in node.variations:
            next_moves.append(move_to_str(board, v.move, settings.ui.move_notation))

        # ------------------------------------------------------------------
        # Build Rich renderables -------------------------------------------
        # ------------------------------------------------------------------
        board_group = Group(*render_board(board, flipped=self._flipped))

        info_lines: list[RenderableType] = []
        info_lines.append(Text(f"Turn: {turn_str}", style="bold"))
        info_lines.append(Text("Last move: ") + Text(last_move_text, style="bold yellow"))

        if next_moves:
            nm_text = Text("Next moves:\n")
            for idx, san in enumerate(next_moves, 1):
                nm_text.append(f"{idx}. {san}\n", style="cyan")
            info_lines.append(nm_text)
        else:
            info_lines.append(Text("Game over.", style="dim"))

        return Group(board_group, Text(), *info_lines)

    def footer(self) -> RenderableType:  # noqa: D401
        return Text("q: quit", style="dim")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _moves_table(moves_san: Iterable[str], *, highlight_index: int | None = None) -> Table:
    tbl = Table(show_header=False, box=None, pad_edge=False)
    col1, col2, col3 = tbl.add_column(), tbl.add_column(), tbl.add_column()  # noqa: F841
    for idx in range(0, len(moves_san), 2):
        move_no = idx // 2 + 1
        white_mv = moves_san[idx]
        black_mv = moves_san[idx + 1] if idx + 1 < len(moves_san) else ""
        style_w = "bold yellow" if highlight_index == idx else ""
        style_b = "bold yellow" if highlight_index == idx + 1 else ""
        tbl.add_row(  # type: ignore[arg-type]
            f"{move_no}.",
            Text(white_mv, style=style_w),
            Text(black_mv, style=style_b),
        )
    return tbl
