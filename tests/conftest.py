"""Pytest configuration – ensure project root is on sys.path so `import blindbase` works
when the package is not yet installed in the active environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ------------------------------------------------------------------
# Optional dependency shims – if running tests in minimal env we stub
# the bits of Pydantic used by BlindBase (BaseSettings and Field).
# ------------------------------------------------------------------
try:
    import pydantic  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    import types

    stub = types.ModuleType("pydantic")

    class _BaseSettings:  # very thin replacement
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def dict(self, *_, **__):  # mimic pydantic
            return self.__dict__

    def _Field(default=None, **_kw):  # noqa: N802 – mimic pydantic.Field
        return default

    stub.BaseSettings = _BaseSettings  # type: ignore[attr-defined]
    stub.Field = _Field  # type: ignore[attr-defined]
    stub.SettingsConfigDict = dict  # type: ignore[attr-defined]
    sys.modules["pydantic"] = stub
    # also provide dummy settings counterpart
    settings_mod = types.ModuleType("pydantic_settings")
    settings_mod.BaseSettings = _BaseSettings  # type: ignore[attr-defined]
    settings_mod.SettingsConfigDict = dict  # type: ignore[attr-defined]
    sys.modules["pydantic_settings"] = settings_mod

# ---------------- tomlkit shim ----------------------
try:
    import tomlkit  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    import types as _t
    _toml = _t.ModuleType("tomlkit")
    def _parse(text):
        return {}
    def _dumps(obj):
        return ""  # minimal
    _toml.parse = _parse  # type: ignore[attr-defined]
    _toml.dumps = _dumps  # type: ignore[attr-defined]
    _toml.TOMLDocument = dict  # type: ignore[attr-defined]
    sys.modules["tomlkit"] = _toml

# -------------- BlindBase settings stub ----------------
import types as _types
from types import SimpleNamespace as _SN
if "blindbase.core.settings" not in sys.modules:
    _bs = _types.ModuleType("blindbase.core.settings")
    from pathlib import Path as _P
    _bs.settings = _SN(
        ui=_SN(move_notation="alg", show_board=True, games_per_page=10),
        broadcasts=_SN(tournaments_limit=5),
        pgn=_SN(directory="/tmp"),
        opening_training=_SN(number_of_attempts=3),
    )
    _bs.CONFIG_PATH = _P("/tmp/blindbase-test.toml")
    sys.modules["blindbase.core.settings"] = _bs
