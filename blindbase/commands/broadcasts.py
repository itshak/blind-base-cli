"""Typer sub-commands for Lichess Broadcasts.

This feature lets users explore Lichess broadcast tournaments / rounds and
follow games live or from PGN snapshots.  The first iteration keeps things
simple:

1. List tournaments (broadcast roots) – limited by settings.broadcasts.tournaments_limit.
2. User picks a tournament -> show rounds.
3. User picks a round -> download PGN (snapshot if not live; otherwise use the
   live PGN stream endpoint but still fallback gracefully).
4. Open a regular GameListPanel followed by GameView.  GameView is extended to
   display clock comments if present (see ui/views/game.py).

NOTE: the Lichess Broadcast API is public and does not require an API token for
read-only access.  Docs: https://lichess.org/api#tag/Broadcasts
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import sys
import tempfile
import time

import requests
import typer
import chess.pgn
from rich.table import Table
from rich.console import Console
from rich.panel import Panel

from blindbase.core.settings import settings
from blindbase.ui.panels.game_list import GameListPanel
from blindbase.core.navigator import GameNavigator
from blindbase.ui.views.game import GameView

__all__ = ["app", "CMD_NAME"]

CMD_NAME = "broadcasts"
app = typer.Typer(help="Follow Lichess broadcast tournaments")

_API_BASE = "https://lichess.org/api/broadcast"
_console = Console()


def _get_json(url: str) -> Any:
    """Return JSON content. Supports regular JSON or NDJSON (newline-delimited)."""
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    try:
        return resp.json()
    except requests.exceptions.JSONDecodeError:
        # fallback: parse NDJSON – many Lichess endpoints stream this format
        import json, io
        objs: list[Any] = []
        for line in io.StringIO(resp.text):
            line = line.strip()
            if not line:
                continue
            try:
                objs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return objs


def _list_broadcasts() -> list[dict[str, Any]]:
    """Return a list of broadcast tournaments ordered by start date desc."""
    data = _get_json(_API_BASE)
    if isinstance(data, list):
        # NDJSON list – each obj has 'tour'
        bcs = [obj.get("tour", obj) for obj in data]
    else:
        # standard JSON object
        bcs = data.get("broadcasts", [])
    # sort by start time descending
    bcs.sort(key=lambda bc: bc.get("startsAt", 0), reverse=True)
    limit = settings.broadcasts.tournaments_limit
    return bcs[:limit]


def _choose_from_table(
    rows: list[tuple[str, ...]],
    title: str,
    headers: list[str],
    prompt: str = "Select item (h for help): ",
    allow_back: bool = False,
) -> int | None:
    """Generic helper to show a rich table and return selected index."""
    if not rows:
        typer.echo("No items to show", err=True)
        return None
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="cyan")
    for head in headers:
        table.add_column(head)
    for idx, row in enumerate(rows, 1):
        table.add_row(str(idx), *row)
    _console.print(Panel(table, title=title, border_style="green"))

    while True:
        choice = input(prompt).strip().lower()
        if choice in {"q", "quit"}:
            return None
        if allow_back and choice == "b":
            return -1
        if choice in {"h", "help"}:
            typer.echo("Enter number to select. q to quit. o to open settings.")
            continue
        if choice == "o":
            from blindbase.ui.panels.settings_menu import run_settings_menu
            run_settings_menu()
            continue
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(rows):
                return idx
            typer.echo("Invalid index")
            continue
        typer.echo("Unknown command – enter number, h, o, b, or q.")


def _download_pgn(url: str) -> str:
    """Return PGN text from *url* (supports streaming)."""
    resp = requests.get(url, stream=True, timeout=10)
    resp.raise_for_status()
    if resp.headers.get("content-type", "").startswith("application/x-ndjson"):
        # Live stream – accumulate until user interrupts
        print("Streaming live PGN…  (Ctrl+C to stop)\n")
        chunks: list[str] = []
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                chunks.append(line + "\n")
                if line.startswith("[Event") or line.startswith("1."):
                    # crude heuristic: once we have header start we can parse progressive
                    pass
        except KeyboardInterrupt:
            pass
        return "".join(chunks)
    else:
        return resp.text


@app.command()
def follow() -> None:  # noqa: C901 complexity ok
    """Interactive broadcast explorer with back-navigation and live settings reload."""
    from datetime import datetime
    while True:  # tournaments loop
        tours = _list_broadcasts()
        rows = [(bc.get("name", "?"),) for bc in tours]
        sel = _choose_from_table(
            rows,
            title="Broadcast Tournaments",
            headers=["Tournament"],
            prompt="Select tournament (h for help): ",
        )
        if sel is None:
            raise typer.Exit()
        tour = tours[sel]
        while True:  # rounds loop
            tour_id = tour["id"]
            tour_data: dict[str, Any] = _get_json(f"{_API_BASE}/{tour_id}")
            rounds: list[dict[str, Any]] = tour_data.get("rounds", [])
            now_ms = int(time.time() * 1000)
            title_rounds = f"Rounds – {tour['name']}"
            round_rows: list[tuple[str, str, str]] = []
            for rnd in rounds:
                rname = rnd.get("name", "?")
                ts = rnd.get("startsAt", 0)
                starts = (
                    datetime.fromtimestamp(ts / 1000).strftime("%b %d %H:%M") if ts else "?"
                )
                if rnd.get("ongoing", False):
                    status = "live"
                elif ts < now_ms:
                    status = "finished"
                else:
                    status = "not started"
                round_rows.append((rname, starts, status))
            rsel = _choose_from_table(
                round_rows,
                title=title_rounds,
                headers=["Round", "Start", "Status"],
                prompt="Select round (h for help, b to back): ",
                allow_back=True,
            )
            if rsel is None:
                raise typer.Exit()
            if rsel == -1:
                break  # back to tournaments
            rnd = rounds[rsel]
            # ------------------------------------------------------------------
            # Download PGN
            # ------------------------------------------------------------------
            pgn_url = (
                rnd.get("pgnUrl")
                or rnd.get("gamesUrl")
                or f"{_API_BASE}/round/{rnd['id']}.pgn"
            )
            if not pgn_url:
                typer.echo("No PGN available for this round", err=True)
                continue  # back to rounds
            pgn_text = _download_pgn(pgn_url)
            if not pgn_text.strip():
                typer.echo("Empty PGN", err=True)
                continue
            # temp file
            tmp = tempfile.NamedTemporaryFile("w+", suffix=".pgn", delete=False)
            tmp.write(pgn_text)
            tmp.flush()
            tmp_path = Path(tmp.name)
            # games
            games: list[chess.pgn.Game] = []
            with open(tmp_path, "r", encoding="utf-8") as fh:
                while True:
                    game = chess.pgn.read_game(fh)
                    if game is None:
                        break
                    games.append(game)
            if not games:
                typer.echo("No games in PGN", err=True)
                continue
            while True:  # games loop
                panel = GameListPanel(
                    games,
                    title=f"Games – {tour['name']} {rnd['name']}",
                    allow_edit=False,
                )
                panel.run()
                if panel.selected_index is None:
                    break  # back to rounds
                game = games[panel.selected_index]
                navigator = GameNavigator(game)
                GameView(navigator).run()
                # after game view returns, go back to games list
    tmp = tempfile.NamedTemporaryFile("w+", suffix=".pgn", delete=False)
    tmp.write(pgn_text)
    tmp.flush()
    tmp_path = Path(tmp.name)

    # ------------------------------------------------------------------
    # 4. Reuse PGN flow --------------------------------------------------
    # ------------------------------------------------------------------
    games = []
    with open(tmp_path, "r", encoding="utf-8") as fh:
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break
            games.append(game)
    if not games:
        typer.echo("No games in PGN", err=True)
        raise typer.Exit(code=1)

    panel = GameListPanel(games, title=f"Games – {tour['name']} {rnd['name']}", allow_edit=False)
    panel.run()
    if panel.selected_index is None:
        # user likely pressed 'b' inside GameListPanel? not supported, just loop back to rounds
        continue
    game = games[panel.selected_index]

    navigator = GameNavigator(game)
    GameView(navigator).run()

    tmp.close()
    # not deleting tempfile automatically for debugging; could unlink here.
    # Path(tmp_path).unlink(missing_ok=True)
