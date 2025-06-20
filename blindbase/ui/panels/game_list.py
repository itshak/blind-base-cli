"""Games list panel – paginated selection of games from a PGN file.

This replaces the legacy *show_game_selection_menu* from ``blindbase.cli``
with a Rich-based, reusable implementation that can also power other
features (e.g. openings training).
"""
from __future__ import annotations

from typing import List

import chess.pgn
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich.text import Text

from blindbase.core.settings import settings

__all__ = ["GameListPanel"]


class GameListPanel:
    """Interactive panel to choose a game from *games*.

    After :py:meth:`run` returns, the selected game index is available via
    :pyattr:`selected_index` (or ``None`` if the user quit).
    """

    def __init__(self, games: List[chess.pgn.Game], *, title: str | None = None, allow_edit: bool = True):
        self.games = games
        self.title = title or "Games List"
        self.page_size = max(1, settings.ui.games_per_page)
        self.allow_edit = allow_edit
        self.selected_index: int | None = None
        self.new_game_headers: dict | None = None
        self.delete_index: int | None = None
        self._console = Console(highlight=False, soft_wrap=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking event-loop.  Returns when a selection is made or user quits."""
        page = 0
        total_games = len(self.games)
        if total_games == 0:
            self._console.print("[red]File contains no games.")
            self._console.input("Press Enter to continue…")
            return
        total_pages = (total_games + self.page_size - 1) // self.page_size

        while True:  # pagination loop
            self._render_page(page, total_pages)
            cmd = self._console.input("Command (h for help): ").strip().lower()
            if cmd in {"h", "help"}:
                self._show_help()
                continue
            if self.allow_edit and cmd == "n":
                self._prompt_new_game()
                return
            if self.allow_edit and cmd.startswith("d ") and cmd[2:].isdigit():
                idx = int(cmd[2:]) - 1
                if 0 <= idx < total_games:
                    self._confirm_delete(idx)
                    return
            if cmd in {"f", "next"} and page + 1 < total_pages:
                page += 1
                continue
            if cmd in {"p", "prev"} and page > 0:
                page -= 1
                continue
            if cmd == "b":
                # back to caller
                return
            if cmd in {"q", "quit"}:
                # leave selected_index as None
                return
            if cmd in {"n", "f", "next"} and page + 1 < total_pages:
                page += 1
                continue
            if cmd in {"p", "b", "prev", "previous"} and page > 0:
                page -= 1
                continue
            if cmd in {"o"}:
                from blindbase.ui.panels.settings_menu import run_settings_menu
                from blindbase.core.settings import settings
                run_settings_menu()
                # Refresh pagination with possibly new page size
                self.page_size = settings.ui.games_per_page
                page = 0
                total_pages = (total_games + self.page_size - 1) // self.page_size
                continue
            if cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < total_games:
                    self.selected_index = idx
                    return
                # fallthrough to error
            self._console.print("[red]Invalid input.")
            self._console.input("Press Enter to continue…")

    def _prompt_new_game(self) -> None:
        from rich.prompt import Prompt
        from rich.panel import Panel
        from rich.table import Table
        import datetime as _dt

        hdrs: dict[str, str] = {}
        self._console.clear()
        self._console.print(Panel("[bold cyan]Add New Game[/bold cyan] – leave blank to skip a field", border_style="cyan"))

        keys = ["Event", "Site", "Date", "Round", "White", "Black", "Result"]
        for key in keys:
            if key == "Result":
                opts = ["1-0", "0-1", "1/2-1/2", "*", "0-0", "bye"]
                tbl = Table(box=None)
                tbl.add_column("#", justify="right", style="bold")
                tbl.add_column("Value")
                for i, o in enumerate(opts, 1):
                    tbl.add_row(str(i), o)
                self._console.print(Panel(tbl, title="Result Options", border_style="green"))
                sel = Prompt.ask("Choose result number", default="4")  # default -> '*'
                if sel.isdigit() and 1 <= int(sel) <= len(opts):
                    val = opts[int(sel) - 1]
                else:
                    val = "*"
                hdrs["Result"] = val
                continue
            default_val = ""
            if key == "Date":
                default_val = _dt.date.today().strftime("%Y.%m.%d")
            val = Prompt.ask(f"{key}", default=default_val).strip()
            if key == "Date" and not val:
                val = default_val
            if val:
                hdrs[key] = val
        self.new_game_headers = hdrs

    def _confirm_delete(self, idx: int) -> None:
        g = self.games[idx]
        white = g.headers.get("White", "?")
        black = g.headers.get("Black", "?")
        confirm = self._console.input(f"Delete game {idx+1}: {white} vs {black}? (Y/n): ").strip().lower()
        if confirm in {"", "y", "yes"}:
            self.delete_index = idx

    def _show_help(self) -> None:
        from blindbase.ui.utils import show_help_panel
        cmds = [
            ("<num>", "open game"),
        ]
        if self.allow_edit:
            cmds.extend([
                ("n", "new game"),
                ("d <num>", "delete game"),
            ])
        cmds.extend([
            ("f", "next page"),
            ("p", "previous page"),
            ("o", "options / settings"),
            ("q", "quit list"),
            ("h", "this help"),
        ])
        show_help_panel(self._console, "Games List – Help", cmds)
        self._console.input("Press Enter to continue…")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_page(self, page: int, total_pages: int) -> None:
        start = page * self.page_size
        end = min(start + self.page_size, len(self.games))
        page_header = Text(f"Page {page + 1} of {total_pages}", style="bold")
        tbl = Table(show_lines=False, box=None)
        tbl.add_column("#", justify="right", style="bold")
        tbl.add_column("White")
        tbl.add_column("Black")
        tbl.add_column("Result", justify="center")
        tbl.add_column("Date", justify="center")
        tbl.add_column("Event")

        for idx in range(start, end):
            g = self.games[idx]
            white = g.headers.get("White", "?")[:15]
            black = g.headers.get("Black", "?")[:15]
            result = g.headers.get("Result", "*")
            date = g.headers.get("Date", "")
            event = g.headers.get("Event", "")[:20]
            tbl.add_row(str(idx + 1), white, black, result, date, event)

        panel = Panel(Align.left(tbl), title=self.title, border_style="blue")
        self._console.clear()
        self._console.print(page_header)
        self._console.print(panel)
