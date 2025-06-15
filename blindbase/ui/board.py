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
    console_width = get_console().size.width
    square_width = 6          # approximate square: 6 cols width vs 3 rows height
    board_pix_width = square_width * 8
    left_pad = max(0, (console_width - board_pix_width) // 2)

    rows: list[Text] = []
    for rank in range(7, -1, -1):
        # Build three lines for each rank to approximate square height
        top = Text(" " * left_pad)
        mid = Text(" " * left_pad)
        bot = Text(" " * left_pad)
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
            bg = "#769656" if is_dark_square else "#EEEED2"
            if piece:
                if piece.color == chess.WHITE:
                    fg_style = "bold white"
                else:
                    fg_style = "black"
            else:
                fg_style = "white" if is_dark_square else "black"

            style = f"{fg_style} on {bg}"
            # top and bottom are spaces
            top.append(" " * square_width, style=f"on {bg}")
            bot.append(" " * square_width, style=f"on {bg}")
            # centre glyph inside width
            pad_left = (square_width - 1) // 2
            pad_right = square_width - 1 - pad_left
            mid.append(" " * pad_left + glyph + " " * pad_right, style=style)
        rows.extend([top, mid, bot])
    return rows 