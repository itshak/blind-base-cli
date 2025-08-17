import sys
import typer

from blindbase.menu import main as _menu_main
from blindbase.commands.pgn import app as pgn_app

app = typer.Typer(add_help_option=False, no_args_is_help=False, help="BlindBase – accessible chess-study CLI")

app.add_typer(pgn_app, name="pgn")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):  # noqa: D401
    """If no subcommand is provided, default to *play*."""
    if ctx.invoked_subcommand is None:
        _menu_main([])


if __name__ == "__main__":
    app() 