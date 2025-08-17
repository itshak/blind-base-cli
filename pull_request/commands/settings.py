"""Settings CLI commands using Typer."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import os

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
            key_name = prefix[:-1]
            if key_name == "engine.path":
                # Treat None, empty string or an obviously invalid value (it contains OS path separators)
                # as meaning the built-in Stockfish binary will be used.
                invalid = obj is None or str(obj).strip() == "" or (isinstance(obj, str) and os.pathsep in obj)
                value_str = "Built-in" if invalid else str(obj)
            else:
                value_str = str(obj)
            tbl.add_row(key_name, value_str)

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
        new_val = value.strip() if isinstance(value, str) else value

    # Special handling: allow resetting engine.path to built-in by entering an
    # empty string or the word "default".
    if key == "engine.path" and (new_val == "" or str(new_val).lower() == "default"):
        new_val = None
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
