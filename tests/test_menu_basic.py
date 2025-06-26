from pathlib import Path
import builtins

import pytest

from blindbase import menu as bb_menu


class DummyExc(SystemExit):
    """Used to intercept Typer exits from dummy commands."""
    def __init__(self, code=0):
        super().__init__(code)

def _dummy(*_args, **_kwargs):
    raise DummyExc(code=0)


class _StubConsole:
    def clear(self):
        pass

    def print(self, *args, **kwargs):
        pass


def test_launch_pgn_returns_to_menu(monkeypatch):
    """_launch_pgn should swallow SystemExit and return cleanly."""
    monkeypatch.setattr("blindbase.commands.pgn.show", _dummy)
    path = Path(__file__)  # arbitrary
    # Should not raise
    bb_menu._launch_pgn("1", path)


def test_select_pgn_lists(monkeypatch, capsys, tmp_path):
    """When user hits Enter at prompt, files in settings dir are listed."""
    # Create dummy pgn dir with files
    data_dir = tmp_path / "pgns"
    data_dir.mkdir()
    (data_dir / "a.pgn").touch()
    (data_dir / "b.pgn").touch()
    monkeypatch.setattr(bb_menu.settings.pgn, "directory", data_dir, raising=False)

    # First input blank -> list; second input "b" to back -> return None
    inputs = iter(["", "b"])
    monkeypatch.setattr(builtins, "input", lambda *_: next(inputs))
    monkeypatch.setattr(bb_menu, "_console", _StubConsole())
    res = bb_menu._select_pgn_file()
    assert res is None
