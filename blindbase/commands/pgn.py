"""Typer sub-commands for PGN operations."""
from __future__ import annotations

from pathlib import Path
import sys

import typer

from blindbase.core import pgn as core_pgn
from blindbase.ui.views.game import GameView
from blindbase.core.navigator import GameNavigator

__all__ = ["app", "CMD_NAME"]

CMD_NAME = "pgn"
app = typer.Typer(help="View or edit PGN files")


@app.command()
def show(file: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Interactively view the first game inside *FILE*.
    
    Shortcuts:
    • Enter – next move
    • b     – back one move
    • f     – flip board
    • q     – quit
    """
    gm = core_pgn.load_games(file)
    if not gm.games:
        typer.echo("File contains no games", err=True)
        raise typer.Exit(code=1)

    game = gm.games[0]
    navigator = GameNavigator(game)
    GameView(navigator).run()

    # After interactive view, prompt to save if edits were made
    if navigator.has_changes:
        choice = input("Save changes? (Y)es/(N)o: ").strip().lower()
        if choice in {"", "y", "yes"}:
            # replace the original game with edited one
            gm.games[0] = navigator.working_game
            core_pgn.save_games(gm)
            print("Changes saved.")
        else:
            print("Changes discarded.")


@app.command(name="list")
def list_games(file: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Print a numbered list of games in *FILE* (quick sanity helper)."""
    gm = core_pgn.load_games(file)
    for idx, g in enumerate(gm.games, 1):
        white = g.headers.get("White", "?")
        black = g.headers.get("Black", "?")
        result = g.headers.get("Result", "*")
        print(f"{idx:>3}  {white} vs {black}  {result}")
    sys.exit(0)
