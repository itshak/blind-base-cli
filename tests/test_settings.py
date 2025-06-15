import os
import json
from blindbase.settings import SettingsManager


def test_settings_load_save(tmp_path):
    settings_file = tmp_path / "settings.json"
    mgr = SettingsManager(settings_filename=str(settings_file))
    # change a value and ensure persistence
    mgr.set("engine_lines_count", 7)
    assert mgr.get("engine_lines_count") == 7
    # reload into new instance
    mgr2 = SettingsManager(settings_filename=str(settings_file))
    assert mgr2.get("engine_lines_count") == 7
    # default untouched
    assert mgr2.get("lichess_moves_count") == 5 