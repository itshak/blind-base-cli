"""Interactive game view replicating legacy CLI commands.

This is *not* feature-complete yet but supports the core navigation / editing
workflow so we can delete legacy PGN handling from ``cli.py`` gradually.
"""
from __future__ import annotations

from pathlib import Path

from blindbase.utils.board_desc import (
    board_summary,
    describe_piece_locations,
    describe_file_or_rank,
)
from typing import Sequence

import chess
from rich.console import Console, Group, RenderableType
from rich.text import Text

from blindbase.core.navigator import GameNavigator
from blindbase.ui.board import render_board

__all__ = ["GameView"]


class GameView:
    """Terminal-interactive PGN viewer/editor.

    Shortcut summary (matches the original script as closely as practical):

    • <Enter> / empty input  – play main-line next move
    • b                      – back one ply
    • f                      – flip board
    • <int>                  – choose variation number (unlimited)
    • p <piece>              – list squares of a piece (KQRBNP)
    • s <file|rank>          – describe a file a-h or rank 1-8
    • r                      – read board aloud (text fallback for now)
    • d <int>                – delete variation (1-based)
    • q                      – quit to caller (raises ExitRequested)
    • h                      – help
    """

    class ExitRequested(Exception):
        """Raised internally when the user exits the game view."""

    def __init__(self, navigator: GameNavigator):
        self.nav = navigator
        self._flip = False
        self._console = Console(highlight=False, soft_wrap=False)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def run(self) -> None:  # blocking loop
        try:
            while True:
                self._render()
                cmd = input("command (h for help): ").strip()
                if not self._handle_command(cmd):
                    continue
        except self.ExitRequested:
            return

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _handle_command(self, cmd: str) -> bool:
        if cmd.lower() in {"q", "quit"}:
            raise self.ExitRequested
        if cmd.lower() in {"h", "help"}:
            self._show_help()
            return False
        if cmd.lower() == "f":
            self._flip = not self._flip
            return False
        if cmd.lower() == "b":
            self.nav.go_back()
            return False
        if cmd.lower() == "t":
            from blindbase.ui.panels.opening_tree import OpeningTreePanel
            panel = OpeningTreePanel(self.nav.get_current_board())
            panel.run()
            mv = getattr(panel, "selected_move", None)
            if mv is not None:
                # apply to navigator
                self.nav.make_move(self.nav.get_current_board().san(mv))
            return False
        if cmd.lower() == "a":
            from blindbase.core.settings import settings
            from blindbase.ui.panels.analysis import AnalysisPanel
            panel = AnalysisPanel(self.nav.get_current_board(), lines=settings.engine.lines)
            panel.run()
            mv = getattr(panel, "selected_move", None)
            if mv is not None:
                self.nav.make_move(self.nav.get_current_board().san(mv))
            return False
        if cmd.lower() == "c":
            from blindbase.core.engine import Engine, EngineError
            try:
                from blindbase.core.engine import score_to_str
                score = Engine.evaluate(self.nav.get_current_board())
                depth = 15  # static for now; could track last depth
                print(f"Engine score: {score_to_str(score)}  (depth {depth})")
            except EngineError as exc:
                print(exc)
            input("Press Enter to continue…")
            return False
        if cmd.lower() == "r":
            self._read_board_aloud()
            return False
        if cmd == "p":
            piece = input("Enter piece (KQRBNP or A for all, case controls colour): ").strip()
            self._list_piece_squares(piece)
            return False
        if cmd.startswith("p "):
            piece = cmd[2:].strip()
            self._list_piece_squares(piece)
            return False
        if cmd == "s":
            spec = input("Enter file (a-h) or rank (1-8): ").strip()
            self._describe_file_or_rank(spec)
            return False
        if cmd.startswith("s "):
            spec = cmd[2:].strip()
            self._describe_file_or_rank(spec)
            return False
        if cmd.startswith("d "):
            try:
                num = int(cmd.split()[1])
                success, msg = self.nav.delete_variation(num)
                print(msg)
            except ValueError:
                print("Invalid variation number.")
            input("Press Enter to continue…")
            return False
        if cmd.isdigit():
            idx = int(cmd)
            self.nav.make_move(cmd)
            return False
        # default: treat as move or mainline advance
        ok, _ = self.nav.make_move(cmd)
        if not ok:
            print("Invalid command or move.")
            input("Press Enter to continue…")
        return False

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render(self) -> None:
        console = self._console
        console.clear()
        board = self.nav.get_current_board()
        # board lines
        for row in render_board(board, flipped=self._flip):
            console.print(row)
        # info section
        turn_txt = "White" if board.turn else "Black"
        console.print(Text("Turn:", style="bold") + Text(f" {turn_txt}", style="yellow"))
        last_move_line = self._last_move_text(board)
        console.print(last_move_line)
        # next moves
        nm_list = self.nav.show_variations()
        if nm_list:
            console.print(Text("Next moves:", style="bold"))
            for line in nm_list:
                console.print(Text(line, style="cyan"))
        else:
            console.print(Text("No next moves.", style="dim"))

    # ------------------------------------------------------------------
    # misc helpers
    # ------------------------------------------------------------------

    def _last_move_text(self, board: chess.Board) -> RenderableType:
        if self.nav.current_node.parent is None:
            return Text("Last move:", style="bold") + Text(" Initial position", style="yellow")
        temp_board = self.nav.current_node.parent.board()
        move = self.nav.current_node.move
        san = temp_board.san(move)
        move_no = temp_board.fullmove_number if temp_board.turn == chess.BLACK else temp_board.fullmove_number - 1
        prefix = f"{move_no}{'...' if temp_board.turn == chess.BLACK else '.'}"
        return Text("Last move:", style="bold") + Text(f" {prefix} {san}", style="yellow")

    def _show_help(self) -> None:
        print("""\nCommands:\n  Enter           next mainline move\n  b               back one move\n  f               flip board\n  <num>           choose variation number\n  p <piece>       list piece squares\n  s <file|rank>   describe a file or rank\n  r               read board (text)\n  d <num>         delete variation\n  t               opening tree\n  a               analysis panel\n  c               engine eval\n  q               quit\n""")
        input("Press Enter to continue…")

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
