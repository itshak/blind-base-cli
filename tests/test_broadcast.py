from blindbase.broadcast import _pgn_stream_url


def test_stream_url():
    url = _pgn_stream_url("ROUNDID", "GAMEID")
    assert url == "https://lichess.org/api/broadcast/round/ROUNDID/game/GAMEID.pgn/stream" 