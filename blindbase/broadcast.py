from __future__ import annotations

import io
import json
import os
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
        """Populate *self.broadcasts* with the list of official broadcasts.

        The endpoint returns Newline-Delimited JSON (NDJSON).  Each line after
        the first may contain another JSON object; the *official* section we
        need is found in the first object.
        """
        try:
            resp = requests.get(BROADCAST_API, stream=True, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"Error fetching broadcasts: {exc}")
            self.broadcasts = []
            return False

        broadcasts: List[dict] = []
        raw_example: str | None = None
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if raw_example is None:
                    raw_example = line
                try:
                    broadcasts.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Skipping unparsable line: {line[:80]}…")
        except requests.RequestException as exc:
            print(f"Stream error: {exc}")
            self.broadcasts = []
            return False

        transformed: List[dict] = []
        for obj in broadcasts:
            if "tour" in obj and "rounds" in obj:
                tour = obj["tour"]
                b_id = tour.get("id")
                name = tour.get("name")
                # use first timestamp in dates list for start date, convert to ISO date
                timestamps = tour.get("dates", [])
                start_date = None
                if timestamps:
                    try:
                        import datetime as _dt
                        start_date = _dt.datetime.utcfromtimestamp(timestamps[0] / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        start_date = str(timestamps[0])
                transformed.append(
                    {
                        "id": b_id,
                        "name": name,
                        "startDate": start_date,
                        "rounds": obj.get("rounds", []),
                    }
                )
            elif "id" in obj and "name" in obj:
                transformed.append(obj)

        self.broadcasts = transformed

        # Debug output (optional; comment out later)
        #        if raw_example:
        #            print("Debug: sample NDJSON line (truncated):", raw_example[:200])
        #        if self.broadcasts:
        #            print("Debug: first broadcast:", json.dumps(self.broadcasts[0], indent=2)[:400])
        return True

    def fetch_rounds(self, broadcast: dict) -> List[dict]:
        """Return list of rounds for a given broadcast object."""
        return broadcast.get("rounds", [])

    def fetch_games(self, round_id: str) -> List[chess.pgn.Game]:
        # Correct endpoint is /broadcast/round/{roundId}.pgn
        url = f"{BROADCAST_API}/round/{round_id}.pgn"
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
            # Extract the standard 8-char Lichess game ID (letters+digits) that appears
            # right after the domain, ignoring any trailing text like ", Norway".
            game_id_match = re.search(r"https://lichess.org/([A-Za-z0-9]{8})", site)
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
    # Ensure the game_id is safely URL-encoded (handles spaces, commas, etc.)
    from urllib.parse import quote
    safe_game_id = quote(game_id, safe="")
    return f"{BROADCAST_API}/round/{round_id}/game/{safe_game_id}.pgn/stream"


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
    stream_url = _pgn_stream_url(round_id, game_id)
    try:
        with requests.get(stream_url, stream=True, timeout=10) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as http_err:
                # If the stream endpoint returns 404, the game is likely finished.
                # Fall back to fetching the full PGN once from the non-stream endpoint.
                if response.status_code == 404:
                    fallback_url = stream_url.replace(".pgn/stream", ".pgn")
                    try:
                        fallback_resp = requests.get(fallback_url, timeout=10)
                        fallback_resp.raise_for_status()
                        update_queue.put(fallback_resp.text)
                        return  # no need to keep streaming
                    except requests.RequestException as exc:
                        if os.environ.get("BB_VERBOSE"):
                            print(f"Error fetching finished game PGN: {exc}")
                        return
                else:
                    raise http_err

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
        if os.environ.get("BB_VERBOSE"):
            print(f"Error streaming PGN: {exc}")