"""Live analysis panel powered by Stockfish."""
from __future__ import annotations

import time
from threading import Thread, Lock
from typing import Optional, List

import chess
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from blindbase.core.engine import Engine


class AnalysisPanel:
    def __init__(self, board: chess.Board, lines: int = 3, target_depth: int = 30):
        self.board = board.copy()
        self.lines = lines
        self.target_depth = target_depth
        self._stop = False
        self._error: Optional[str] = None
        self._lock = Lock()
        self._pv_list: List[List[chess.Move]] = []
        self._scores: List[chess.engine.Score] = []
        self._current_depth = 0

    # ---------------- Worker -----------------
    def _worker(self):
        try:
            from blindbase.core.engine import _SingletonEngine
            eng = _SingletonEngine.get()
            engine_name = eng.id.get("name", "Engine")
            self.engine_name = engine_name  # type: ignore[attr-defined]
            depth = 6
            while not self._stop:
                info = eng.analyse(
                    self.board,
                    chess.engine.Limit(depth=depth),
                    multipv=self.lines,
                )
                if isinstance(info, list):
                    infos = info
                else:
                    infos = [info]

                with self._lock:
                    self._current_depth = depth
                    # sort by multipv order
                    infos.sort(key=lambda d: d.get("multipv", 1))
                    self._pv_list = [d.get("pv", []) for d in infos]
                    self._scores = [d.get("score") for d in infos]

                depth += 2
                if depth > 99:
                    depth = 99  # cap depth


        except Exception as exc:
            self._error = str(exc)
        finally:
            self._stop = True

    # ---------------- UI -----------------
    def run(self):
        console = Console()
        Thread(target=self._worker, daemon=True).start()
        final_panel = None
        import sys, select
        with Live(console=console, screen=False, auto_refresh=False, refresh_per_second=4) as live:
            while not self._stop:
                live.update(Group(Text(""), self._render_panel()))
                live.refresh()
                # check for user keypress without blocking; pyenv/IDE terminal can
                # report stdin as ready even when no real keystroke is pending.
                if select.select([sys.stdin], [], [], 0)[0]:
                    # Read a single line – will be empty string if nothing was
                    # actually entered.  Ignore such spurious wake-ups.
                    line = sys.stdin.readline()
                    if line:
                        self._user_choice = line.strip()
                        self._stop = True
                        break
                time.sleep(0.25)
            if self._error:
                final_panel = Align.center(f"[red]{self._error}")
            else:
                final_panel = Group(Text(""), self._render_panel(final=True))
        # after Live closes, prompt user (panel already displayed in terminal)
        # freeze lines at moment of prompt to avoid race with engine updates
        with self._lock:
            frozen_pv = [pv[:] for pv in self._pv_list]
        choice = console.input("Enter engine line to make it on board or press Enter to exit: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(frozen_pv):
                mv = frozen_pv[idx - 1][0] if frozen_pv[idx - 1] else None
                if mv:
                    self.selected_move: chess.Move | None = mv  # type: ignore[attr-defined]

            

    def _render_panel(self, final: bool = False):
        from blindbase.core.engine import score_to_str

        if self._error:
            return Align.center(f"[red]{self._error}")
        with self._lock:
            pv_list = self._pv_list[:]
            scores = self._scores[:]
            depth = self._current_depth
        tbl = Table(box=None)
        tbl.add_column("Line", justify="right")
        tbl.add_column("Score", justify="right")
        tbl.add_column("Engine line")
        if not pv_list:
            return Panel(Align.center("[cyan]Waiting for engine…"), title="Engine", border_style="green")
        for idx, (pv_moves, sc) in enumerate(zip(pv_list, scores), 1):
            b = self.board.copy()
            san_parts = []
            for mv in pv_moves:
                move_no = b.fullmove_number
                san = b.san(mv)
                if b.turn == chess.WHITE:
                    san_parts.append(f"{move_no}. {san}")
                else:
                    san_parts.append(f"{move_no}… {san}")
                b.push(mv)
            san_line = " ".join(san_parts)
            # truncate to fit console width
            import shutil
            width = shutil.get_terminal_size((120, 20)).columns
            max_len = max(width - 40, 20)
            if len(san_line) > max_len:
                san_line = san_line[: max_len - 3] + "…"
            score_str = score_to_str(sc) if sc else "-"
            tbl.add_row(str(idx), score_str, san_line)
        header = f"{getattr(self, 'engine_name', 'Engine')}  Depth: {self._current_depth}  Lines: {self.lines}"
        instruction = Align.center("[dim]Press Enter to show command prompt")
        return Panel(Group(instruction, tbl), title=header, border_style="green")
