from blindbase.core.settings import settings as default_settings


def test_settings_roundtrip():
    SettingsClass = type(default_settings)
    s = SettingsClass()
    # change value
    s.engine.lines = 7
    # serialise + rehydrate
    data = s.model_dump()
    s2 = Settings(**data)
    assert s2.engine.lines == 7
    # default untouched
    assert s2.opening_tree.lichess_moves == 5