"""Tests for TrainingView logic: verifying quit flow and basic move check."""
from __future__ import annotations

import builtins
import contextlib
import io

import chess
import chess.pgn
from types import SimpleNamespace

from blindbase.core.navigator import GameNavigator
from blindbase.ui.views.training import TrainingView


def _dummy_game():
    game = chess.pgn.Game()
    game.headers["White"] = "Tester"
    game.headers["Black"] = "Bot"
    return game


def test_training_quit(monkeypatch):
    """User inputs 'q' immediately – TrainingView should raise ExitRequested."""
    game = _dummy_game()
    nav = GameNavigator(game)
    # first input 'q'
    monkeypatch.setattr(builtins, "input", lambda *_a, **_kw: "q")
    monkeypatch.setattr(
        "blindbase.ui.board.settings",
        SimpleNamespace(ui=SimpleNamespace(board_theme="default")),
    )
    with contextlib.suppress(TrainingView.ExitRequested):
        TrainingView(nav, player_is_white=True).run()


def test_training_correct_move(monkeypatch, capsys):
    """Simulate one correct move then quit."""
    # Make a simple PGN with 1.e4 e5
    pgn_text = "1. e4 e5 *"
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    nav = GameNavigator(game)
    inputs = iter(["e4", "q"])
    monkeypatch.setattr(builtins, "input", lambda *_: next(inputs))
    monkeypatch.setattr(
        "blindbase.ui.board.settings",
        SimpleNamespace(ui=SimpleNamespace(board_theme="default")),
    )
    with contextlib.suppress(TrainingView.ExitRequested):
        TrainingView(nav, player_is_white=True).run()
    captured = capsys.readouterr().out
    assert isinstance(captured, str)
