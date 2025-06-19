"""Helpers for textual board descriptions (r, p, s commands).

These functions are extracted from the legacy CLI and adapted to work with the
centralised settings system and ``move_format`` helpers so that all
coordinates respect the user's *move_notation* preference (SAN, NATO, Anna,
etc.).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import chess

from blindbase.core.settings import settings
from blindbase.utils.move_format import format_square

_STYLE = settings.ui.move_notation


# ---------------------------------------------------------------------------
# Notation helpers (square formatting only) – we reuse ``format_square``
# ---------------------------------------------------------------------------

def _fmt(square: str) -> str:
    """Return *square* formatted according to the current notation setting with capitalised file when using anna/nato/literate."""
    out = format_square(square, _STYLE)
    # Capitalise first letter for Anna/NATO styles (e.g. "eva 8" -> "Eva 8") so it reads better
    return out.capitalize()


# ---------------------------------------------------------------------------
# Piece / square utilities
# ---------------------------------------------------------------------------

_PIECE_PRIORITY = {
    chess.KING: 0,
    chess.QUEEN: 1,
    chess.ROOK: 2,
    chess.BISHOP: 3,
    chess.KNIGHT: 4,
    chess.PAWN: 5,
}

_PIECE_LETTERS = {
    chess.PAWN: "",
    chess.ROOK: "R",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.QUEEN: "Q",
    chess.KING: "K",
}


def get_squares_for_piece(board: chess.Board, piece_code: str) -> List[str]:
    """Return list of *square* names for *piece_code*.

    piece_code examples::
        'N' – white knights
        'k' – black king
        'A' – all white pieces
        'a' – all black pieces
    """
    if not piece_code:
        return []

    code = piece_code[0]
    # Handle special A/a meaning all pieces of a colour
    if code in ("A", "a"):
        colour = chess.WHITE if code.isupper() else chess.BLACK
        return [chess.square_name(sq) for sq, pc in board.piece_map().items() if pc.color == colour]

    piece_type_map = {
        "p": chess.PAWN,
        "n": chess.KNIGHT,
        "b": chess.BISHOP,
        "r": chess.ROOK,
        "q": chess.QUEEN,
        "k": chess.KING,
    }
    piece_type = piece_type_map.get(code.lower())
    if piece_type is None:
        return []

    colour = chess.WHITE if code.isupper() else chess.BLACK
    return [
        chess.square_name(sq)
        for sq, pc in board.piece_map().items()
        if pc.color == colour and pc.piece_type == piece_type
    ]


def describe_piece_locations(board: chess.Board, piece_code: str) -> str:
    """Natural-language description of *piece_code* locations."""
    style = settings.ui.move_notation

    if piece_code.lower() == "a":
        colour = chess.WHITE if piece_code.isupper() else chess.BLACK
        pieces = []
        for sq, pc in board.piece_map().items():
            if pc.color != colour:
                continue
            piece_word = chess.piece_name(pc.piece_type).capitalize()
            disp = (
                f"{piece_word} {_fmt(chess.square_name(sq))}"
            )
            pieces.append((_PIECE_PRIORITY[pc.piece_type], disp))
        pieces.sort(key=lambda t: (t[0], t[1]))
        colour_str = "White" if colour == chess.WHITE else "Black"
        if pieces:
            return f"{colour_str} pieces: " + ", ".join(d for _, d in pieces) + "."
        return f"{colour_str} pieces: none."

    colour_str = "White" if piece_code.isupper() else "Black"
    squares = get_squares_for_piece(board, piece_code)

    singular = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}
    plural = {k: v + ("s" if not v.endswith("s") else "") for k, v in singular.items()}

    if not squares:
        return f"There are no {colour_str.lower()} {plural[piece_code.lower()]}."

    squares_fmt = ", ".join(_fmt(sq) for sq in squares)
    if len(squares) == 1:
        article = singular[piece_code.lower()].capitalize()
        return f"{colour_str} {article} is on {squares_fmt}."
    return f"{colour_str} {plural[piece_code.lower()]} are on {squares_fmt}."


def describe_file_or_rank(board: chess.Board, spec: str) -> str:
    """Description of pieces on a file (a-h) or rank (1-8)."""
    spec = spec.strip().lower()
    # Square specification (e.g. "a8")
    if len(spec) == 2 and spec[0] in "abcdefgh" and spec[1] in "12345678":
        try:
            sq = chess.parse_square(spec)
        except ValueError:
            return "Invalid square specification."
        pc = board.piece_at(sq)
        if pc is None:
            return f"Square {_fmt(spec)} is empty."
        colour = "White" if pc.color == chess.WHITE else "Black"
        piece_name = chess.piece_name(pc.piece_type).capitalize()
        return f"{colour} {piece_name} on {_fmt(spec)}."

    # File or rank specification
    if not spec or spec not in "abcdefgh12345678":
        return "Invalid file or rank specification."

    pieces_on_line: list[tuple[str, chess.Piece]] = []
    for sq, pc in board.piece_map().items():
        name = chess.square_name(sq)
        if spec in "abcdefgh" and name[0] == spec:
            pieces_on_line.append((name, pc))
        elif spec in "12345678" and name[1] == spec:
            pieces_on_line.append((name, pc))

    if not pieces_on_line:
        line_str = f"file {spec}" if spec in "abcdefgh" else f"rank {spec}"
        return f"No pieces on {line_str}."

    # Sort in ascending rank/file order for consistency
    pieces_on_line.sort(key=lambda t: (t[0][1], t[0][0]))
    parts: list[str] = []
    for sq_name, pc in pieces_on_line:
        colour = "White" if pc.color == chess.WHITE else "Black"
        piece_name = chess.piece_name(pc.piece_type)
        parts.append(f"{colour} {piece_name.capitalize()} {_fmt(sq_name)}")
    line_str = f"file {spec}" if spec in "abcdefgh" else f"rank {spec}"
    return f"Pieces on {line_str}: " + "; ".join(parts) + "."


def board_summary(board: chess.Board) -> str:
    """Return a two-line summary listing White then Black pieces from King to Pawn."""
    out_lines: list[str] = []
    for colour in (chess.WHITE, chess.BLACK):
        parts: list[str] = []
        for piece_type in (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
            squares = [chess.square_name(sq) for sq, pc in board.piece_map().items() if pc.color == colour and pc.piece_type == piece_type]
            if not squares:
                continue
            if piece_type == chess.PAWN:
                for sq in squares:
                    parts.append(f"Pawn {_fmt(sq)}")
            else:
                squares_str = ", ".join(_fmt(sq) for sq in squares)
                piece_name = chess.piece_name(piece_type).capitalize()
                parts.append(f"{piece_name} {squares_str}")
        colour_str = "White" if colour == chess.WHITE else "Black"
        line = f"{colour_str}: " + "; ".join(parts) + "."
        out_lines.append(line)
    return "\n".join(out_lines)
