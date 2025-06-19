"""Settings CLI commands using Typer."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from blindbase.core.settings import settings, CONFIG_PATH

app = typer.Typer(help="Manage BlindBase settings")
console = Console()


@app.command("list")
def list_settings(section: Optional[str] = typer.Argument(None, help="Optional section to list (engine, opening, ui)")):
    """Display current settings."""
    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("Key")
    tbl.add_column("Value")

    def _walk(prefix: str, obj):
        if hasattr(obj, "model_dump"):
            for k, v in obj.model_dump().items():
                _walk(f"{prefix}{k}.", v)
        else:
            tbl.add_row(prefix[:-1], str(obj))

    target = getattr(settings, section) if section else settings
    _walk("" if section else "", target)

    console.print(tbl)


@app.command("get")
def get_setting(key: str):
    """Print value of a single setting (dot notation)."""
    parts = key.split(".")
    val = settings
    for p in parts:
        val = getattr(val, p)
    console.print(val)


@app.command("set")
def set_setting(key: str, value: str):
    """Set a setting. Type is inferred from current value."""
    parts = key.split(".")
    obj = settings
    for p in parts[:-1]:
        obj = getattr(obj, p)
    attr = parts[-1]
    current = getattr(obj, attr)
    # simple cast
    if isinstance(current, bool):
        new_val = value.lower() in ("1", "true", "yes", "on")
    elif isinstance(current, int):
        new_val = int(value)
    elif isinstance(current, Path):
        new_val = Path(value).expanduser()
    else:
        new_val = value
    # basic enum validation
    if isinstance(current, str) and isinstance(new_val, str):
        choices = None
        if key.endswith("move_notation"):
            choices = ["san", "uci", "nato", "anna"]
        if choices and new_val not in choices:
            console.print(f"[red]Invalid value. Choose from {choices}[/red]")
            raise typer.Exit(1)
    setattr(obj, attr, new_val)
    settings.save()
    console.print("[green]Saved.[/green]")


@app.command("path")
def show_path():
    """Show the path to the active settings file."""
    console.print(Path(CONFIG_PATH).expanduser())
