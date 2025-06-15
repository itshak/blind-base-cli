import sys
import typer

from blindbase.cli import main as legacy_main

app = typer.Typer(add_help_option=False, no_args_is_help=False, help="BlindBase – accessible chess-study CLI")


@app.command("play", help="Open the interactive TUI. Optional PGN file and Stockfish path override.")
def play(
    pgn: str = typer.Argument(None, metavar="[PGN_FILE]", help="PGN file to open"),
    engine: str = typer.Option(None, "--engine", "-e", help="Path to Stockfish binary"),
):
    # When called programmatically (e.g., app()), Typer injection is bypassed and the
    # default value may be a Typer ArgumentInfo object instead of None.  Normalise:
    if not isinstance(pgn, str):
        pgn = None
    if not isinstance(engine, str):
        engine = None
    # Reconstruct argv expected by legacy_main
    sys.argv = ["blindbase-legacy"] + ([pgn] if pgn else []) + ([engine] if engine else [])
    legacy_main()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):  # noqa: D401
    """If no subcommand is provided, default to *play*."""
    if ctx.invoked_subcommand is None:
        play(None, None)


if __name__ == "__main__":
    app() 