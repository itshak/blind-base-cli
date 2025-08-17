"""Interactive main menu and PGN selector for BlindBase.

This lightweight module glues the already-refactored Typer sub-commands
(`blindbase.commands`) together so that end-users can simply run

    blindbase                # open menu
    blindbase mygames.pgn    # open viewer
    blindbase -t rep.pgn     # open training mode

without having to know the underlying command hierarchy.

It is intentionally dependency-free (only uses the stdlib) so it can run
very early and in restricted environments (e.g. PyInstaller one-file
bundles where Rich may take noticeable time to import).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from blindbase.core.settings import settings
from blindbase.commands import pgn as pgn_cmd
from blindbase.commands import broadcasts as broadcasts_cmd
from blindbase.ui.panels.settings_menu import run_settings_menu
from blindbase.sounds_util import play_sound
from blindbase.ui.utils import clear_screen_and_prepare_for_new_content

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.text import Text

_console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _select_pgn_file() -> Optional[Path]:  # noqa: C901 complexity okay
    """Return a PGN file chosen by the user or *None* if they cancel.

    Two modes:
    1. Prompt the user for a full path.
    2. If they press Enter with an empty input, list *.pgn* files found in the
       directory configured in ``settings.pgn.directory`` and let the user pick
       by number.
    """
    while True:
        inp = input("Enter full path to PGN file (leave blank to list default directory): ").strip()
        if inp:
            path = Path(inp).expanduser()
            if not path.is_file():
                print("File not found – try again.")
                play_sound("decline.mp3")
                continue
            return path
        # --- directory listing branch -----------------------------------
        pgn_dir = Path(settings.pgn.directory).expanduser()
        if not pgn_dir.exists():
            print(f"Directory {pgn_dir} does not exist; update it in Settings (option 'o').")
            return None
        files = sorted(pgn_dir.glob("*.pgn"))
        if not files:
            print(f"No .pgn files found in {pgn_dir}.")
            return None
        play_sound("notify.mp3")
        clear_screen_and_prepare_for_new_content()
        tbl = Table(show_header=False, box=None, padding=(0,1))
        tbl.add_column(justify="right", style="cyan")
        tbl.add_column()
        for idx, f in enumerate(files, 1):
            tbl.add_row(f"{idx}.", f.name)
        _console.print(Panel(tbl, title=f"PGN files in {pgn_dir}", border_style="green"))
        choice = input("Select number (b to back): ").strip().lower()
        if choice == "b":
            play_sound("click.mp3")
            return None
        if not choice.isdigit():
            print("Invalid input – please enter a number.")
            play_sound("decline.mp3")
            continue
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            play_sound("click.mp3")
            return files[idx]
        print("Number out of range.")
        play_sound("decline.mp3")


# ---------------------------------------------------------------------------
# Main Menu
# ---------------------------------------------------------------------------

def _render_main_menu() -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="center", ratio=1)
    table.add_row(Text("BlindBase", style="bold magenta", justify="center"))
    opts = [
        ("1", "View PGN"),
        ("2", "Opening training"),
        ("3", "Broadcasts"),
        ("o", "Settings"),
        ("a", "About"),
        ("q", "Quit"),
    ]
    menu_tbl = Table.grid(padding=1)
    menu_tbl.add_column(justify="right", style="cyan")
    menu_tbl.add_column()
    for key, label in opts:
        menu_tbl.add_row(key + ")", label)
    panel = Panel(menu_tbl, title="BlindBase", border_style="green")
    clear_screen_and_prepare_for_new_content()
    _console.print(panel)

def _run_main_menu() -> None:
    while True:
        _render_main_menu()
        choice = input("Select option: ").strip().lower()
        if choice == "q":
            play_sound("click.mp3")
            break
        if choice == "a":
            _show_about()
            continue
        if choice == "o":
            run_settings_menu()
            continue
        if choice == "3":
            _launch_broadcasts()
            continue
        if choice in {"1", "2"}:
            pgn_path = _select_pgn_file()
            if pgn_path is None:
                play_sound("click.mp3")
                continue
            _launch_pgn(choice, pgn_path)
            continue
        _console.print("[red]Invalid choice.[/red]")
        play_sound("decline.mp3")
        input("Press Enter to continue…")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Launch helpers ------------------------------------------------------------
# ---------------------------------------------------------------------------

def _launch_pgn(mode_choice: str, pgn_path: Path) -> None:
    """Run PGN viewer or trainer safely, returning to menu on exit."""
    play_sound("notify.mp3")
    import click
    func = pgn_cmd.show if mode_choice == "1" else pgn_cmd.train
    try:
        func(pgn_path)
    except (SystemExit, click.exceptions.Exit) as exc:  # swallow Typer exit
        # If exit code non-zero (e.g. empty PGN) show message
        if getattr(exc, "exit_code", 0):
            _console.print("[yellow]Action cancelled or file had no games.[/yellow]")
            input("Press Enter to continue…")


def _launch_broadcasts() -> None:
    play_sound("notify.mp3")
    import click
    try:
        broadcasts_cmd.follow()
    except (SystemExit, click.exceptions.Exit):
        # just return to menu
        pass


def _show_about() -> None:
    play_sound("notify.mp3")
    panel = Panel(
        Text(
            (
                f"BlindBase CLI v{__import__('blindbase').__version__}\n"
                "Developer: Alexey Streltsov\n"
                "A command-line chess study suite for visually-impaired players.\n"
                "GitHub: https://github.com/itshak/blind-base-cli"
            ),
            justify="left",
        ),
        title="About",
        border_style="blue",
    )
    clear_screen_and_prepare_for_new_content()
    _console.print(panel)
    input("Press Enter to return…")

# ---------------------------------------------------------------------------
# CLI entry-point with quick argument dispatch
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """Entry-point for ``python -m blindbase`` or ``blindbase`` script."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("pgn", nargs="?", help="PGN file to open")
    parser.add_argument("--train", "-t", action="store_true", help="Train openings instead of viewing")
    parser.add_argument("--broadcasts", "-b", action="store_true", help="Open broadcasts explorer directly")
    args, _unknown = parser.parse_known_args(argv)

    if args.broadcasts:
        _launch_broadcasts()
        _run_main_menu()
        return

    if args.pgn:
        pgn_path = Path(args.pgn)
        if not pgn_path.exists():
            print(f"File not found: {pgn_path}", file=sys.stderr)
            sys.exit(1)
        mode_choice = "2" if args.train else "1"
        _launch_pgn(mode_choice, pgn_path)
        _run_main_menu()
        return

    # No arguments → interactive main menu
    _run_main_menu()


if __name__ == "__main__":  # pragma: no cover
    main()
