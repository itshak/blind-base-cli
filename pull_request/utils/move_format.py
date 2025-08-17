"""Helpers to display moves and squares according to *move_notation* setting.

Subset copied from legacy CLI implementation – supports san (default), uci,
'nato' (NATO alphabet square names), and 'anna' (literate chess square names).
"""
from __future__ import annotations

import re
import chess

__all__ = [
    "format_square",
    "move_to_str",
]

_nato_files = {
    "a": "Alpha",
    "b": "Bravo",
    "c": "Charlie",
    "d": "Delta",
    "e": "Echo",
    "f": "Foxtrot",
    "g": "Golf",
    "h": "Hotel",
}

_anna_files = {
    "a": "Anna",
    "b": "Bella",
    "c": "Cesar",
    "d": "David",
    "e": "Eva",
    "f": "Felix",
    "g": "Gustav",
    "h": "Hector",
}


def format_square(sq: str, style: str) -> str:
    """Return *sq* formatted according to chosen style."""
    f = sq[0]
    r = sq[1]
    style = style.lower()
    if style == "uci" or style == "san":
        return sq
    if style == "nato":
        return f"{_nato_files[f]} {r}"
    if style in {"literate", "anna"}:
        return f"{_anna_files[f]} {r}"
    return sq


def move_to_str(board: chess.Board, move: chess.Move, style: str) -> str:  # noqa: C901 – legacy logic
    """Return a human-readable representation of *move* respecting *style*."""
    style = (style or "san").lower()
    if style == "uci":
        return move.uci()
    san = board.san(move)
    if style == "san":
        return san

    out = san
    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)
    for sq in {from_sq, to_sq}:
        out = out.replace(sq, format_square(sq, style))

    if style in {"literate", "nato", "anna"}:
        piece_map = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight"}
        if san[0] in piece_map:
            out = piece_map[san[0]] + " " + out[1:]
        if "x" in san:
            out = out.replace("x", " takes ", 1)
        # handle pawn capture leading file for anna
        if style in {"anna"} and san[0] in _anna_files and " takes " in out:
            out = _anna_files[san[0]] + " " + out[1:]
        out = re.sub(r"\s+", " ", out)
    return out.strip()
