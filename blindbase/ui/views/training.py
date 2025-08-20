from __future__ import annotations
import random
from typing import Dict, Optional
import chess
from rich.console import Console, RenderableType
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

from blindbase.core.settings import settings
from blindbase.ui.utils import show_help_panel, colorize, colorize_style
from blindbase.ui.board import render_board
from blindbase.mll_trainer import OpeningTrainer
from blindbase.utils.board_desc import (
    board_summary,
    describe_piece_locations,
    describe_file_or_rank,
)
from blindbase.sounds_util import play_sound

__all__ = ["TrainingView"]


class TrainingView:
    """Run an opening training session for one game."""

    class ExitRequested(Exception):
        def __init__(self, show_summary: bool = True):
            self.show_summary = show_summary

    class _Restart(Exception):
        """Internal helper to restart training without exiting."""
        pass

    def __init__(self, trainer: OpeningTrainer, player_is_white: bool):
        self.trainer = trainer
        self.player_is_white = player_is_white
        self._console = Console()
        # orient board so player's side is at bottom
        self._flip = not player_is_white
        # Remember computer's random choices per node so session is stable
        self._ai_choices: Dict[chess.pgn.GameNode, chess.Move] = {}
        # stats
        self.correct_guesses = 0
        self.failed_guesses = 0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking loop for the session. Respects replay choice."""
        while True:
            try:
                while True:
                    self._render()
                    if self.trainer.is_at_eol():
                        raise self.ExitRequested(True)
                    board = self.trainer.get_current_board()
                    player_turn = board.turn == (chess.WHITE if self.player_is_white else chess.BLACK)
                    if player_turn:
                        self._handle_player_turn()
                    else:
                        self._handle_computer_turn()
            except self.ExitRequested as exc:
                if exc.show_summary:
                    if self._show_summary():
                        self._reset_session()
                        continue
                # propagate to caller (GameList) by re-raising
                raise

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        console = self._console
        console.clear()
        board = self.trainer.get_current_board()
        # Header (same as GameView header)
        white = self.trainer.working_game.headers.get("White", "?")
        black = self.trainer.working_game.headers.get("Black", "?")
        console.print(Text(f"{white} vs {black}", style=colorize_style("bold yellow")))
        console.print()
        if settings.ui.show_board:
            for row in render_board(board, flipped=self._flip):
                console.print(row)
        turn_txt = "White" if board.turn else "Black"
        you_or_opp = "your turn" if (board.turn == chess.WHITE) == self.player_is_white else "opponent's turn"
        console.print(Text("Turn:", style=colorize_style("bold")) + Text(f" {turn_txt} ({you_or_opp})", style=colorize_style("yellow")))
        last_move = self._last_move_text(board)
        console.print(last_move)

    def _last_move_text(self, board: chess.Board) -> RenderableType:
        if self.trainer.current_node.parent is None:
            return Text("Last move:", style=colorize_style("bold")) + Text(" Initial position", style=colorize_style("yellow"))
        temp_board = self.trainer.current_node.parent.board()
        move = self.trainer.current_node.move
        from blindbase.utils.move_format import move_to_str
        san = move_to_str(temp_board, move, settings.ui.move_notation)
        move_no = temp_board.fullmove_number if temp_board.turn == chess.BLACK else temp_board.fullmove_number - 1
        prefix = f"{move_no}{'...' if temp_board.turn == chess.BLACK else '.'}"
        return Text("Last move:", style=colorize_style("bold")) + Text(f" {prefix} {san}", style=colorize_style("yellow"))

    # ------------------------------------------------------------------
    # Player turn
    # ------------------------------------------------------------------

    def _handle_player_turn(self) -> None:
        max_attempts = settings.opening_training.number_of_attempts
        attempts = 0
        while attempts < max_attempts:
            cmd = self._console.input("Your move (h for help): ").strip()
            if not self._dispatch_common(cmd):
                continue
            if self.trainer.try_my_move(cmd):
                self.correct_guesses += 1
                play_sound("correct.mp3")
                self.trainer.review_my_move(0.1) # lrate
                return
            else:
                self._console.print(colorize("Incorrect – try again.", "red"))
                play_sound("incorrect.mp3")
                attempts += 1
        self.failed_guesses += 1
        correct_move_san = self.trainer.review_my_move(0.1) # lrate
        self._console.print(colorize(f"Correct move was {correct_move_san}. Moving on…", "yellow"))

    def _handle_computer_turn(self) -> None:
        move_san = self.trainer.select_max_loss_move()
        self._console.print(Text(f"Opponent will play: {move_san}", style=colorize_style("cyan")))
        play_sound("move-opponent.mp3")
        while True:
            cmd = self._console.input("Enter to continue (h for help): ").strip()
            if cmd == "":
                break
            if not self._dispatch_common(cmd):
                continue
        self.trainer.go_forward(move_san)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dispatch_common(self, cmd: str) -> bool:
        lc = cmd.lower()
        if lc in {"q", "quit"}:
            raise self.ExitRequested(False)
        if lc in {"h", "help"}:
            self._show_help()
            self._render()
            return False
        if lc == "o":
            from blindbase.ui.panels.settings_menu import run_settings_menu
            run_settings_menu()
            self._render()
            return False
        if lc == "f":
            self._flip = not self._flip
            self._render()
            return False
        if lc == "r":
            self._read_board_aloud()
            self._render()
            return False
        if lc.startswith("p "):
            self._list_piece_squares(lc.split()[1])
            self._render()
            return False
        if lc.startswith("s "):
            self._describe_file_or_rank(lc.split()[1])
            self._render()
            return False
        return True  # cmd not handled

    def _parse_move_input(self, text: str) -> chess.Move:
        board = self.trainer.get_current_board()
        # Try SAN as-is
        try:
            return board.parse_san(text)
        except ValueError:
            pass
        # Try SAN with capitalised piece letter (e.g. nf6 -> Nf6)
        if text and text[0] in "kqrbn":
            try:
                return board.parse_san(text[0].upper() + text[1:])
            except ValueError:
                pass
        # Try SAN lower-case pawn/file style (e.g. e4)
        try:
            return board.parse_san(text.lower())
        except ValueError:
            pass
        # Try UCI
        try:
            return board.parse_uci(text.lower())
        except ValueError as exc:
            raise ValueError from exc
        # If all fail, raise
        raise ValueError('Invalid move format')

    # ------------------------------------------------------------------
    # Extra blind-friendly helpers (share logic with GameView)
    # ------------------------------------------------------------------

    def _reset_session(self) -> None:
        # Go back to initial position using navigator
        self.trainer.go_root()
        self.correct_guesses = 0
        self.failed_guesses = 0

    # ------------------------------------------------------------------
    # Extra blind-friendly helpers (share logic with GameView)
    # ------------------------------------------------------------------

    def _read_board_aloud(self):
        text = board_summary(self.trainer.get_current_board())
        print(text)
        input("Press Enter to continue…")

    def _list_piece_squares(self, piece: str):
        desc = describe_piece_locations(self.trainer.get_current_board(), piece)
        print(desc)
        input("Press Enter to continue…")

    def _describe_file_or_rank(self, spec: str):
        text = describe_file_or_rank(self.trainer.get_current_board(), spec)
        print(text)
        input("Press Enter to continue…")

    def _show_help(self):
        cmds = [
            ("<move>", "enter your move (SAN)"),
            ("f", "flip board"),
            ("p <piece>", "list piece squares"),
            ("s <file|rank>", "describe file or rank"),
            ("r", "read board (text)"),
            ("o", "options / settings"),
            ("h", "help"),
            ("q", "quit training"),
        ]
        show_help_panel(self._console, "Training Commands", cmds)
        self._console.input("Press Enter to continue…")

    def _show_summary(self) -> bool:
        play_sound("achievement.mp3")
        total = self.correct_guesses + self.failed_guesses
        pct = (self.correct_guesses / total) * 100 if total else 0
        tbl = Table(show_header=False, box=None, pad_edge=False)
        tbl.add_row("Total guesses", str(total))
        tbl.add_row("Correct", colorize(f"{self.correct_guesses}", "green"))
        tbl.add_row("Incorrect", colorize(f"{self.failed_guesses}", "red"))
        tbl.add_row("Accuracy", colorize(f"{pct:.0f}%", "bold yellow"))
        panel = Panel(tbl, title=colorize("Training Summary", "bold cyan"), border_style=colorize_style("bright_blue"))
        self._console.print()
        self._console.print(panel)
        choice = self._console.input(f"[bold]Train this line again?[/] ({colorize('y', 'green')}/n): ").strip().lower()
        return choice.startswith("y")