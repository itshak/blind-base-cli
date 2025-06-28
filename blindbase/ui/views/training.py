"""Opening training interactive view.

Allows the user to play through the main-line of a PGN game while the
computer replies with random moves from the available variations.
"""
from __future__ import annotations

import random
from typing import Dict, Optional
import chess
from rich.console import Console, RenderableType
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

from blindbase.core.settings import settings
from blindbase.ui.utils import show_help_panel
from blindbase.ui.board import render_board
from blindbase.core.navigator import GameNavigator
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

    def __init__(self, navigator: GameNavigator, player_is_white: bool):
        self.nav = navigator
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
                    board = self.nav.get_current_board()
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
        board = self.nav.get_current_board()
        # Header (same as GameView header)
        white = self.nav.working_game.headers.get("White", "?")
        black = self.nav.working_game.headers.get("Black", "?")
        console.print(Text(f"{white} vs {black}", style="bold yellow"))
        console.print()
        if settings.ui.show_board:
            for row in render_board(board, flipped=self._flip):
                console.print(row)
        turn_txt = "White" if board.turn else "Black"
        you_or_opp = "your turn" if (board.turn == chess.WHITE) == self.player_is_white else "opponent's turn"
        console.print(Text("Turn:", style="bold") + Text(f" {turn_txt} ({you_or_opp})", style="yellow"))
        last_move = self._last_move_text(board)
        console.print(last_move)

    def _last_move_text(self, board: chess.Board) -> RenderableType:
        if self.nav.current_node.parent is None:
            return Text("Last move:", style="bold") + Text(" Initial position", style="yellow")
        temp_board = self.nav.current_node.parent.board()
        move = self.nav.current_node.move
        from blindbase.utils.move_format import move_to_str
        san = move_to_str(temp_board, move, settings.ui.move_notation)
        move_no = temp_board.fullmove_number if temp_board.turn == chess.BLACK else temp_board.fullmove_number - 1
        prefix = f"{move_no}{'...' if temp_board.turn == chess.BLACK else '.'}"
        return Text("Last move:", style="bold") + Text(f" {prefix} {san}", style="yellow")

    # ------------------------------------------------------------------
    # Player turn
    # ------------------------------------------------------------------

    def _handle_player_turn(self) -> None:
        node = self.nav.current_node
        if not node.variations:
            self._console.print("[green]End of line – training complete![/green]")
            raise self.ExitRequested
        expected_move = node.variations[0].move  # main line
        max_attempts = settings.opening_training.number_of_attempts
        attempts = 0
        while attempts < max_attempts:
            cmd = self._console.input("Your move (h for help): ").strip()
            if not self._dispatch_common(cmd):
                continue  # handled help/settings/etc.
            try:
                move = self._parse_move_input(cmd)
            except ValueError:
                self._console.print("[red]Invalid move format.[/red]")
                play_sound("illegal.mp3")
                attempts += 1
                continue
            if move == expected_move:
                san_std = self.nav.get_current_board().san(move)
                self.nav.make_move(san_std)
                self.correct_guesses += 1
                play_sound("correct.mp3")
                return
            else:
                self._console.print("[red]Incorrect – try again.[/red]")
                play_sound("incorrect.mp3")
                attempts += 1
        # failed 3 times – show correct move and push it
        self.failed_guesses += 1
        from blindbase.utils.move_format import move_to_str
        san_disp = move_to_str(self.nav.get_current_board(), expected_move, settings.ui.move_notation)
        self._console.print(f"[yellow]Correct move was {san_disp}. Moving on…[/yellow]")
        san_std = self.nav.get_current_board().san(expected_move)
        self.nav.make_move(san_std)

    # ------------------------------------------------------------------
    # Computer turn
    # ------------------------------------------------------------------

    def _handle_computer_turn(self) -> None:
        node = self.nav.current_node
        if not node.variations:
            self._console.print("[green]Line finished![/green]")
            raise self.ExitRequested
        # choose or fetch stored move
        if node in self._ai_choices:
            mv = self._ai_choices[node]
        else:
            mv = random.choice([v.move for v in node.variations])
            self._ai_choices[node] = mv
        from blindbase.utils.move_format import move_to_str
        san_disp = move_to_str(self.nav.get_current_board(), mv, settings.ui.move_notation)
        san_std = self.nav.get_current_board().san(mv)
        self._console.print(Text(f"Opponent will play: {san_disp}", style="cyan"))
        play_sound("move-opponent.mp3")
        while True:
            cmd = self._console.input("Enter to continue (h for help): ").strip()
            if cmd == "":
                break
            if not self._dispatch_common(cmd):
                continue  # handled command (help etc.)
        self.nav.make_move(san_std)

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
        board = self.nav.get_current_board()
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
        while self.nav.current_node.parent is not None:
            self.nav.go_back()
        self.correct_guesses = 0
        self.failed_guesses = 0

    # ------------------------------------------------------------------
    # Extra blind-friendly helpers (share logic with GameView)
    # ------------------------------------------------------------------

    def _read_board_aloud(self):
        text = board_summary(self.nav.get_current_board())
        print(text)
        input("Press Enter to continue…")

    def _list_piece_squares(self, piece: str):
        desc = describe_piece_locations(self.nav.get_current_board(), piece)
        print(desc)
        input("Press Enter to continue…")

    def _describe_file_or_rank(self, spec: str):
        text = describe_file_or_rank(self.nav.get_current_board(), spec)
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
        tbl.add_row("Correct", f"[green]{self.correct_guesses}[/]")
        tbl.add_row("Incorrect", f"[red]{self.failed_guesses}[/]")
        tbl.add_row("Accuracy", f"[bold yellow]{pct:.0f}%[/]")
        panel = Panel(tbl, title="[bold cyan]Training Summary[/]", border_style="bright_blue")
        self._console.print()
        self._console.print(panel)
        choice = self._console.input("[bold]Train this line again?[/] ([green]y[/]/n): ").strip().lower()
        return choice.startswith("y")
