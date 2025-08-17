"""Opening tree panel – shows master-game statistics for current board."""
from __future__ import annotations

from typing import List

import chess
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align

from blindbase.core.settings import settings
from blindbase.utils.move_format import move_to_str

from blindbase.core.opening_tree import get_master_moves, OpeningStat


class OpeningTreePanel:
    def __init__(self, board: chess.Board):
        self.board = board.copy()

    def run(self) -> None:
        console = Console()
        try:
            top_n = settings.opening_tree.lichess_moves
            stats: List[OpeningStat] = get_master_moves(self.board, top_n=top_n)
        except Exception as exc:
            console.print(f"[red]Failed to fetch opening stats: {exc}")
            console.input("Press Enter to continue…")
            return
        tbl = Table(title="Opening Tree", box=None, show_lines=False)
        tbl.add_column("#", justify="right")
        tbl.add_column("Move")
        tbl.add_column("Games", justify="right")
        tbl.add_column("White", justify="right")
        tbl.add_column("Draw", justify="right")
        tbl.add_column("Black", justify="right")
        for idx, (san, w, d, b) in enumerate(stats, 1):
            try:
                mv = self.board.parse_san(san)
                disp = move_to_str(self.board, mv, settings.ui.move_notation)
            except Exception:
                disp = san
            total = w + d + b
            if total == 0:
                total = 1  # avoid div0
            tbl.add_row(
                str(idx),
                disp,
                str(total),
                f"{w * 100 // total}%",
                f"{d * 100 // total}%",
                f"{b * 100 // total}%",
            )
        console.print(Panel(tbl, border_style="blue"))
        choice = console.input("Select move number or press Enter to continue… ").strip()
        if not choice:
            return
        if choice.isdigit() and 1 <= int(choice) <= len(stats):
            idx = int(choice) - 1
            san = stats[idx][0]
            board = self.board.copy()
            try:
                mv = board.parse_san(san)
                self.board.push(mv)
                # pass the move back via attribute for caller to consume
                self.selected_move: chess.Move | None = mv  # type: ignore[attr-defined]
            except Exception as exc:
                console.print(f"[red]Could not apply move: {exc}")
                console.input("Press Enter to continue…")
        else:
            console.print("[red]Invalid input.")
            console.input("Press Enter to continue…")
