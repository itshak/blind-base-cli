import io
import chess
import chess.pgn
from blindbase.navigator import GameNavigator


def _make_game():
    pgn = "1. e4 e5 2. Nf3 Nc6 *"
    game = chess.pgn.read_game(io.StringIO(pgn))
    return game


def test_make_move_and_back():
    game = _make_game()
    nav = GameNavigator(game)
    # starting board
    start_fen = nav.get_current_board().fen()
    success, _ = nav.make_move("e4")
    assert success
    assert nav.get_current_board().fullmove_number == 1
    # one ply made
    assert nav.get_current_board().fen() != start_fen
    # go back
    assert nav.go_back()
    assert nav.get_current_board().fen() == start_fen 