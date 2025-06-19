import os
import sys
from typing import Sequence, Tuple, Iterable
from rich.table import Table
from rich.panel import Panel

UI_SCREEN_BUFFER_HEIGHT = 35  # preserved for compatibility


def clear_screen_and_prepare_for_new_content(is_first_draw: bool = False):
    """Clear the terminal, respecting platform differences.

    Copied verbatim from the original monolith so other modules can import it
    without creating circular dependencies.
    """
    if is_first_draw:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")
        return

    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")
    sys.stdout.flush()


def show_help_panel(console, title: str, commands: Sequence[tuple[str, str]]) -> None:
    """Render a consistent Rich-styled help panel.

    Parameters
    ----------
    console : rich.console.Console
        The console to render to.
    title : str
        Panel title.
    commands : Sequence[tuple[str, str]]
        Iterable of (key, description) pairs.
    """
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("Key", style="bold green", no_wrap=True)
    table.add_column("Action", style="yellow")
    for key, desc in commands:
        table.add_row(key, desc)
    panel = Panel(table, title=f"[bold cyan]{title}[/bold cyan]", border_style="cyan")
    console.print(panel)