"""Small wrapper around Lichess Opening Explorer API.

We query master games stats for the current board FEN.  Caches responses in
memory to avoid spamming the API during a session.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import List, Tuple

import chess

__all__ = ["OpeningStat", "get_master_moves"]

API_URL = "https://explorer.lichess.ovh/masters"

OpeningStat = Tuple[str, int, int, int]  # san, whiteWins, draws, blackWins


def _fetch_master_moves(fen: str, top_n: int) -> List[OpeningStat]:
    params = urllib.parse.urlencode({"fen": fen})
    url = f"{API_URL}?{params}"
    with urllib.request.urlopen(url, timeout=8) as resp:
        data = json.load(resp)
    out: List[OpeningStat] = []
    moves_raw = data.get("moves", []) if isinstance(data, dict) else data
    for mv in moves_raw[:top_n]:
        san = mv.get("san") or mv.get("uci", "")
        w = mv.get("white", mv.get("whiteWins", 0)) or 0
        d = mv.get("draws", mv.get("draw", 0)) or 0
        b = mv.get("black", mv.get("blackWins", 0)) or 0
        out.append((san, w, d, b))
    return out

# Cache by FEN string (board is unhashable)

@lru_cache(maxsize=2048)
def get_master_moves_cached(fen: str, top_n: int) -> tuple[OpeningStat, ...]:
    return tuple(_fetch_master_moves(fen, top_n))


def get_master_moves(board: chess.Board, top_n: int = 10) -> List[OpeningStat]:
    """Return top_n master moves for *board* FEN."""
    fen = board.fen()
    return list(get_master_moves_cached(fen, top_n))
