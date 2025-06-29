"""
Background streaming of Lichess broadcast games.
"""
import threading
import requests
import chess.pgn
import io
from typing import Callable

class GameStreamer(threading.Thread):
    """
    Connects to a Lichess broadcast game stream and calls a callback with updated game objects.
    """
    def __init__(self, round_id: str, game_id: str, update_callback: Callable[[chess.pgn.Game], None]):
        super().__init__(daemon=True)
        self._round_id = round_id
        self._game_id = game_id
        self._update_callback = update_callback
        self._stop_event = threading.Event()
        self.url = f"https://lichess.org/api/broadcast/round/{self._round_id}/game/{self._game_id}.pgn"

    def run(self):
        """
        Runs the streaming loop, fetching the PGN and calling the callback on update.
        """
        try:
            with requests.get(self.url, stream=True, timeout=15) as resp:
                resp.raise_for_status()
                pgn_stream = io.StringIO()
                for line in resp.iter_lines(decode_unicode=True):
                    if self._stop_event.is_set():
                        break
                    if line:
                        pgn_stream.write(line + '\n')
                        # The stream from lichess sends the entire PGN each time.
                        # We can re-parse the whole thing.
                        pgn_stream.seek(0)
                        game = chess.pgn.read_game(pgn_stream)
                        if game:
                            self._update_callback(game)
                        pgn_stream.seek(0, io.SEEK_END)
        except requests.RequestException:
            # Silently exit on connection errors.
            pass

    def stop(self):
        """
        Signals the thread to stop.
        """
        self._stop_event.set()
