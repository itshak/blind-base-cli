import os
import shutil
from datetime import datetime
from typing import List, Optional

import chess
import chess.pgn

__all__ = ["GameManager"]


class GameManager:
    """CRUD operations for PGN files, including pagination helpers."""

    def __init__(self, pgn_filename: str):
        self.pgn_filename = pgn_filename
        self.games: List[chess.pgn.Game] = []
        self.current_game_index: int = 0
        self.load_games()

    # --- original implementation copied verbatim -------------------------

    def load_games(self):
        self.games = []
        pgn_dir = os.path.dirname(self.pgn_filename)
        if pgn_dir:
            os.makedirs(pgn_dir, exist_ok=True)
        if not os.path.exists(self.pgn_filename):
            print(f"PGN file {self.pgn_filename} not found. Creating new.")
            try:
                with open(self.pgn_filename, "w", encoding="utf-8") as pgn_file:
                    pass
            except IOError as e:
                print(f"Error creating PGN file '{self.pgn_filename}': {e}")
                return
        else:
            print(f"Loading games from {self.pgn_filename}...")
        try:
            with open(self.pgn_filename, "r", encoding="utf-8") as pgn_file:
                while True:
                    offset = pgn_file.tell()
                    try:
                        game = chess.pgn.read_game(pgn_file)
                    except Exception as e:
                        line = pgn_file.readline()
                        while line and not line.startswith("[Event "):
                            line = pgn_file.readline()
                        if line:
                            pgn_file.seek(pgn_file.tell() - len(line.encode("utf-8")))
                            continue
                        else:
                            break
                    if game is None:
                        break
                    self.games.append(game)
            print(f"Loaded {len(self.games)} games from {self.pgn_filename}")
            if not self.games:
                self.current_game_index = 0
            elif self.current_game_index >= len(self.games):
                self.current_game_index = len(self.games) - 1
        except Exception as e:
            print(f"Error loading PGN file: {e}")
            self.games = []
            self.current_game_index = 0

    def save_games(self) -> bool:
        try:
            backup_filename = self.pgn_filename + ".backup"
            if os.path.exists(self.pgn_filename):
                shutil.copy2(self.pgn_filename, backup_filename)
            with open(self.pgn_filename, "w", encoding="utf-8") as pgn_file:
                for game in self.games:
                    exporter = chess.pgn.FileExporter(pgn_file)
                    game.accept(exporter)
            print(f"Games saved to {self.pgn_filename}")
            return True
        except Exception as e:
            print(f"Error saving PGN file: {e}")
            return False

    def add_new_game(self):
        from blindbase.ui.utils import clear_screen_and_prepare_for_new_content  # lazy import to avoid circular

        clear_screen_and_prepare_for_new_content()
        print("--- Add New Game ---")
        white_name = input("White player name (default: Unknown): ").strip() or "Unknown"
        black_name = input("Black player name (default: Unknown): ").strip() or "Unknown"
        white_elo = input("White ELO (optional): ").strip()
        black_elo = input("Black ELO (optional): ").strip()
        result = input("Result (1-0, 0-1, 1/2-1/2, * default): ").strip()
        if result not in ["1-0", "0-1", "1/2-1/2", "*"]:
            result = "*"
        event = input("Event (optional): ").strip()
        site = input("Site (optional): ").strip()
        date = (
            input(f"Date (YYYY.MM.DD, Enter for {datetime.now().strftime('%Y.%m.%d')}): ").strip()
            or datetime.now().strftime("%Y.%m.%d")
        )
        round_num = input("Round (optional): ").strip()
        game: chess.pgn.Game = chess.pgn.Game()
        game.headers["White"] = white_name
        game.headers["Black"] = black_name
        game.headers["Result"] = result
        game.headers["Date"] = date
        if white_elo.isdigit():
            game.headers["WhiteElo"] = white_elo
        if black_elo.isdigit():
            game.headers["BlackElo"] = black_elo
        if event:
            game.headers["Event"] = event
        if site:
            game.headers["Site"] = site
        if round_num:
            game.headers["Round"] = round_num
        self.games.append(game)
        self.current_game_index = len(self.games) - 1
        print(f"\nNew game added! Total games: {len(self.games)}")
        input("Press Enter to continue...")
        return True 