from __future__ import annotations

import chess
from rich.console import Console
from rich.text import Text

# Singleton console reused across renders
_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(highlight=False, soft_wrap=False)
    return _console


UNICODE_PIECES = {
    chess.PAWN: {True: "♙", False: "♟"},
    chess.ROOK: {True: "♖", False: "♜"},
    chess.KNIGHT: {True: "♘", False: "♞"},
    chess.BISHOP: {True: "♗", False: "♝"},
    chess.QUEEN: {True: "♕", False: "♛"},
    chess.KING: {True: "♔", False: "♚"},
}


def render_board(board: chess.Board, use_unicode: bool = True) -> list[Text]:
    """Return list of Text rows to print for *board*."""
    left_pad = 0  # left align board with other content

    rows: list[Text] = []
    for rank in range(7, -1, -1):
        line = Text(" " * left_pad)
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            if piece:
                if use_unicode:
                    glyph = UNICODE_PIECES[piece.piece_type][piece.color]
                else:
                    glyph = piece.symbol().upper() if piece.color == chess.WHITE else piece.symbol()
            else:
                glyph = " "

            is_dark_square = (file + rank) % 2 == 1
            # Swap colours so that d1 becomes light square (light and dark reversed)
            bg = "#EEEED2" if is_dark_square else "#769656"
            if piece:
                if piece.color == chess.WHITE:
                    fg_style = "bold white"
                else:
                    fg_style = "black"
            else:
                # adjust text colour for reversed background choice
                fg_style = "white" if bg == "#769656" else "black"

            style = f"{fg_style} on {bg}"
            line.append(f"{glyph} ", style=style)   # glyph plus trailing space
        rows.append(line)
    return rows 