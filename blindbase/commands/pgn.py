"""Typer sub-commands for PGN operations."""
from __future__ import annotations

from pathlib import Path
import sys

import typer

from blindbase.core import pgn as core_pgn
from blindbase.ui.views.game import GameView
from blindbase.core.navigator import GameNavigator

from blindbase.ui.views.training import TrainingView
from blindbase.sounds_util import play_sound
from blindbase.ui.utils import clear_screen_and_prepare_for_new_content
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
    # ------------------------------------------------------------------
    # Load PGN file ------------------------------------------------------
    # ------------------------------------------------------------------
    play_sound("notify.mp3")
    gm = core_pgn.load_games(file)
    if not gm.games:
        typer.echo("File contains no games", err=True)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Let user pick a game via Rich menu -------------------------------
    # ------------------------------------------------------------------
    from blindbase.ui.panels.game_list import GameListPanel  # local import to avoid cycles

    while True:
        clear_screen_and_prepare_for_new_content()
        panel = GameListPanel(gm.games, title=f"Games in {file.name}")
        panel.run()
        # Handle deletion
        if panel.delete_index is not None:
            idx = panel.delete_index
            del gm.games[idx]
            core_pgn.save_games(gm)
            typer.echo(f"Deleted game {idx+1}.")
            continue  # back to list
        # Handle new game
        if panel.new_game_headers is not None:
            import chess.pgn
            new_game = chess.pgn.Game()
            for k, v in panel.new_game_headers.items():
                new_game.headers[k] = v
            gm.games.append(new_game)
            sel_idx = len(gm.games) - 1
        else:
            if panel.selected_index is None:
                # user cancelled list -> exit command
                play_sound("click.mp3")
                raise typer.Exit(code=0)
            sel_idx = panel.selected_index
        assert sel_idx is not None  # mypy hint
        game = gm.games[sel_idx]
        play_sound("click.mp3")

        # ------------------------------------------------------------------
        # Launch interactive GameView --------------------------------------
        # ------------------------------------------------------------------
        play_sound("game-start.mp3")
        navigator = GameNavigator(game)
        GameView(navigator).run()  # returns when user quits game view
        play_sound("click.mp3")

        # ------------------------------------------------------------------
        # Save changes back to PGN if needed --------------------------------
        # ------------------------------------------------------------------
        if navigator.has_changes:
            choice = input("Save changes? (Y)es/(N)o: ").strip().lower()
            if choice in {"", "y", "yes"}:
                gm.games[sel_idx] = navigator.working_game
                core_pgn.save_games(gm)
                print("Changes saved.")
            else:
                print("Changes discarded.")
        # After playing a game, loop back to list for another selection


@app.command()
def train(file: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Opening training mode using PGN main lines."""
    play_sound("notify.mp3")
    gm = core_pgn.load_games(file)
    if not gm.games:
        typer.echo("File contains no games", err=True)
        raise typer.Exit(code=1)
    from blindbase.ui.panels.game_list import GameListPanel
    # choose game
    panel = GameListPanel(gm.games, title=f"Select game to train from {file.name}", allow_edit=False)
    panel.run()
    if panel.selected_index is None:
        play_sound("click.mp3")
        raise typer.Exit()
    game = gm.games[panel.selected_index]
    play_sound("click.mp3")
    # choose color
    from rich.prompt import Prompt
    color = Prompt.ask("Train as (w)hite or (b)lack?", choices=["w", "b"], default="w")
    player_is_white = color == "w"
    nav = GameNavigator(game)
    try:
        TrainingView(nav, player_is_white).run()
    except TrainingView.ExitRequested:
        play_sound("click.mp3")
        # back to list instead of quitting whole app
        return train(file)


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
