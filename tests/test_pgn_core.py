from pathlib import Path

from blindbase.core import pgn as core_pgn

TEST_PGN = Path(__file__).parent.parent / "test.pgn"


def test_load_games_nonempty():
    gm = core_pgn.load_games(TEST_PGN)
    # ensure at least one game exists in the bundled sample file
    assert len(gm.games) > 0, "test.pgn should contain at least one game"
