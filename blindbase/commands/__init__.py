"""Modern Typer-based command hierarchy (work-in-progress).

This lightweight wrapper will progressively replace the legacy `blindbase.cli`
monolith.  For now it only exposes an empty Typer application so that Phase 0
and Phase 1 of the refactor compile successfully.
"""
from __future__ import annotations

from . import pgn, settings, broadcasts  # register sub-apps

import typer

app = typer.Typer(add_completion=False, help="BlindBase experimental commands")


# Attach sub-commands -------------------------------------------------------
app.add_typer(pgn.app, name=pgn.CMD_NAME)
app.add_typer(settings.app, name="settings")
app.add_typer(broadcasts.app, name="broadcasts")


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context):
    """BlindBase CLI (refactor in progress).

    Prints this help message when run with no sub-command so that
    `python -m blindbase.commands --help` works even before commands are
    implemented.
    """
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:  # pragma: no cover – simple runner
    """Entry-point used by `python -m blindbase.commands`."""
    app()


if __name__ == "__main__":  # pragma: no cover – direct execution fallback
    main()
