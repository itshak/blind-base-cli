"""Tests for PGN command helpers (list and show)."""
from __future__ import annotations

import builtins
import contextlib
from pathlib import Path
import io

import chess.pgn

from blindbase.commands import pgn as pgn_cmd


def _make_temp_pgn(tmp_path: Path) -> Path:
    game = chess.pgn.Game()
    game.headers["Event"] = "UnitTest"
    game.end()
    pfile = tmp_path / "one.pgn"
    with open(pfile, "w", encoding="utf-8") as fh:
        print(game, file=fh)
    return pfile


def test_list_games(tmp_path, capsys):
    pfile = _make_temp_pgn(tmp_path)
    # Should not raise
    with contextlib.suppress(SystemExit):
        pgn_cmd.list_games(pfile)
    out = capsys.readouterr().out
    assert "Games" in out or "vs" in out


def test_show_game_quick_quit(monkeypatch, tmp_path):
    pfile = _make_temp_pgn(tmp_path)
    # simulate immediate quit in viewer 'q'
    inputs = iter(["q"])
    monkeypatch.setattr(builtins, "input", lambda *_: next(inputs))
    monkeypatch.setattr("blindbase.ui.panels.game_list.GameListPanel.run", lambda self: (_ for _ in ()).throw(SystemExit))
    with contextlib.suppress(SystemExit):
        pgn_cmd.show(pfile)
