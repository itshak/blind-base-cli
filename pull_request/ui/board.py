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


from blindbase.core.settings import settings
from blindbase.ui.themes import BOARD_THEMES


UNICODE_PIECES = {
    chess.PAWN: {True: "♙", False: "♟"},
    chess.ROOK: {True: "♖", False: "♜"},
    chess.KNIGHT: {True: "♘", False: "♞"},
    chess.BISHOP: {True: "♗", False: "♝"},
    chess.QUEEN: {True: "♕", False: "♛"},
    chess.KING: {True: "♔", False: "♚"},
}


def render_board(board: chess.Board, use_unicode: bool = True, *, flipped: bool = False) -> list[Text]:
    """Return list of Text rows to print for *board*."""
    left_pad = 0  # left align board with other content

    rows: list[Text] = []
    rank_iter = range(8) if flipped else range(7, -1, -1)
    file_iter_template = list(range(7, -1, -1)) if flipped else list(range(8))
    for rank in rank_iter:
        line = Text(" " * left_pad)
        file_iter = file_iter_template
        for file in file_iter:
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            if piece:
                if use_unicode:
                    glyph = UNICODE_PIECES[piece.piece_type][piece.color]
                else:
                    glyph = piece.symbol().upper() if piece.color == chess.WHITE else piece.symbol()
            else:
                glyph = " "

            is_dark_square = (file + rank) % 2 != 1
            
            current_theme = BOARD_THEMES[settings.ui.board_theme]
            light_col = current_theme.light_square_color
            dark_col = current_theme.dark_square_color

            bg = dark_col if is_dark_square else light_col
            if piece:
                if piece.color == chess.WHITE:
                    fg_style = current_theme.piece_color_white
                else:
                    fg_style = current_theme.piece_color_black
            else:
                # adjust text colour for reversed background choice
                fg_style = "white" if bg == dark_col else "black"

            style = f"{fg_style} on {bg}"
            line.append(f"{glyph} ", style=style)   # glyph plus trailing space
        rows.append(line)
    return rows 