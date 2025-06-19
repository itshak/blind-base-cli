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

from blindbase.ui.utils import show_help_panel
from blindbase.ui.board import render_board
from blindbase.core.navigator import GameNavigator

__all__ = ["TrainingView"]


class TrainingView:
    """Run an opening training session for one game."""

    class ExitRequested(Exception):
        pass

    def __init__(self, navigator: GameNavigator, player_is_white: bool):
        self.nav = navigator
        self.player_is_white = player_is_white
        self._console = Console()
        self._flip = False
        # Remember computer's random choices per node so session is stable
        self._ai_choices: Dict[chess.pgn.GameNode, chess.Move] = {}
        # stats
        self.correct_guesses = 0
        self.failed_guesses = 0

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            while True:
                self._render()
                board = self.nav.get_current_board()
                is_player_turn = board.turn == (chess.WHITE if self.player_is_white else chess.BLACK)
                if is_player_turn:
                    self._handle_player_turn()
                else:
                    self._handle_computer_turn()
        except self.ExitRequested:
            self._show_summary()

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
        san = temp_board.san(move)
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
        attempts = 0
        while attempts < 3:
            cmd = self._console.input("Your move (h for help): ").strip()
            if not self._dispatch_common(cmd):
                continue  # handled help/settings/etc.
            try:
                move = self._parse_move_input(cmd)
            except ValueError:
                self._console.print("[red]Invalid move format.[/red]")
                attempts += 1
                continue
            if move == expected_move:
                self.nav.make_move(cmd)
                self.correct_guesses += 1
                return
            else:
                self._console.print("[red]Incorrect – try again.[/red]")
                attempts += 1
        # failed 3 times – show correct move and push it
        self.failed_guesses += 1
        san = self.nav.get_current_board().san(expected_move)
        self._console.print(f"[yellow]Correct move was {san}. Moving on…[/yellow]")
        self.nav.make_move(san)

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
        san = self.nav.get_current_board().san(mv)
        self._console.print(Text(f"Opponent will play: {san}", style="cyan"))
        self._console.input("Press Enter to continue…")
        self.nav.make_move(san)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dispatch_common(self, cmd: str) -> bool:
        lc = cmd.lower()
        if lc in {"q", "quit"}:
            raise self.ExitRequested
        if lc in {"h", "help"}:
            self._show_help()
            return False
        if lc == "o":
            from blindbase.ui.panels.settings_menu import run_settings_menu
            run_settings_menu()
            return False
        if lc == "f":
            self._flip = not self._flip
            return False
        return True  # cmd not handled

    def _parse_move_input(self, text: str) -> chess.Move:
        board = self.nav.get_current_board()
        try:
            move = board.parse_san(text)
        except ValueError as exc:
            raise ValueError from exc
        return move

    def _show_help(self):
        cmds = [
            ("<move>", "enter your move (SAN)"),
            ("f", "flip board"),
            ("o", "options / settings"),
            ("h", "help"),
            ("q", "quit training"),
        ]
        show_help_panel(self._console, "Training Commands", cmds)

    def _show_summary(self):
        total = self.correct_guesses + self.failed_guesses
        if total == 0:
            return
        pct = self.correct_guesses * 100 / total
        self._console.print(f"You answered {self.correct_guesses}/{total} correctly ({pct:.0f}%).")
        self._console.input("Press Enter to exit…")
