from __future__ import annotations

import io
import json
import queue
import re
import threading
from typing import List, Optional, Tuple

import requests
import chess
import chess.pgn


__all__ = [
    "BroadcastManager",
    "stream_game_pgn",
]


BROADCAST_API = "https://lichess.org/api/broadcast"


def _safe_request_json(url: str, timeout: int = 5):
    """Wrapper around requests.get that converts JSON and handles errors."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        print(f"Error fetching {url}: {exc}")
        return None


class BroadcastManager:
    """Fetch broadcast metadata (tournaments, rounds, games) from Lichess."""

    def __init__(self):
        self.broadcasts: List[dict] = []
        self.selected_broadcast: Optional[dict] = None
        self.selected_round: Optional[dict] = None
        self.selected_game: Optional[chess.pgn.Game] = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def fetch_broadcasts(self) -> bool:
        """Populate *self.broadcasts* with the list of official broadcasts."""
        data = _safe_request_json(BROADCAST_API)
        if not data:
            self.broadcasts = []
            return False
        self.broadcasts = data.get("official", [])
        return True

    def fetch_rounds(self, broadcast: dict) -> List[dict]:
        """Return list of rounds for a given broadcast object."""
        return broadcast.get("rounds", [])

    def fetch_games(self, round_id: str) -> List[chess.pgn.Game]:
        url = f"{BROADCAST_API}/{round_id}.pgn"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Error fetching games: {exc}")
            return []

        pgn_io = io.StringIO(response.text)
        games: List[chess.pgn.Game] = []
        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
            site = game.headers.get("Site", "")
            game_id_match = re.search(r"https://lichess.org/(\w+)", site)
            if game_id_match:
                game_id = game_id_match.group(1)
                game.game_id = game_id  # type: ignore[attr-defined]
            games.append(game)
        return games


# ----------------------------------------------------------------------
# Streaming helpers
# ----------------------------------------------------------------------

def _pgn_stream_url(round_id: str, game_id: str) -> str:
    """Build the *correct* PGN streaming URL.

    According to the Lichess API docs, the path does *not* include the
    broadcast ID.
    """
    return f"{BROADCAST_API}/round/{round_id}/game/{game_id}.pgn/stream"


def stream_game_pgn(
    round_id: str,
    game_id: str,
    update_queue: "queue.Queue[str]",
    stop_event: threading.Event,
):
    """Continuously stream PGN chunks into *update_queue* until *stop_event*.

    This is a drop-in replacement for the original implementation, but with
    the corrected URL format.
    """
    url = _pgn_stream_url(round_id, game_id)
    try:
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()
            pgn = ""
            for line in response.iter_lines(decode_unicode=True):
                if stop_event.is_set():
                    break
                if line:
                    pgn += line + "\n"
                elif pgn:  # Blank line indicates end of current PGN chunk
                    update_queue.put(pgn)
                    pgn = ""
            if pgn:
                update_queue.put(pgn)
    except Exception as exc:
        print(f"Error streaming PGN: {exc}") 