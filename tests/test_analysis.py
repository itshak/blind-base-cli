from types import SimpleNamespace
from blindbase.analysis import get_analysis_block_height


def test_analysis_height():
    settings = SimpleNamespace(get=lambda k: {"engine_lines_count":3, "analysis_block_padding":2}[k])
    assert get_analysis_block_height(settings) == 1 + 3 + 2 