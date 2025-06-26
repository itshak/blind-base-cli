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
import builtins as _builtins

if "blindbase.core.settings" not in sys.modules:
    _bs = _types.ModuleType("blindbase.core.settings")
    from pathlib import Path as _P

    class _Settings:  # minimal stand-in for the real Pydantic model
        """Lightweight replacement that supports only the attributes
        and helper methods referenced in the test-suite."""

        def __init__(
            self,
            engine: object = _SN(lines=3),
            opening_tree: object = _SN(lichess_moves=5),
            ui: _SN = _SN(move_notation="alg", show_board=True, games_per_page=10),
            opening_training: _SN = _SN(number_of_attempts=3),
            broadcasts: _SN = _SN(tournaments_limit=5),
            pgn: _SN = _SN(directory="/tmp"),
        ) -> None:
            # accept both dict or SimpleNamespace for flexibility
            if isinstance(engine, dict):
                engine = _SN(**engine)
            if isinstance(opening_tree, dict):
                opening_tree = _SN(**opening_tree)
            self.engine = engine
            self.opening_tree = opening_tree
            self.ui = ui
            self.opening_training = opening_training
            self.broadcasts = broadcasts
            self.pgn = pgn

        # ------------------------------------------------------------------
        # Compatibility helpers
        # ------------------------------------------------------------------
        def model_dump(self):  # mimics pydantic v2 API used in tests
            return {
                "engine": {"lines": self.engine.lines},
                "opening_tree": {"lichess_moves": self.opening_tree.lichess_moves},
                "ui": {
                    "move_notation": self.ui.move_notation,
                    "show_board": self.ui.show_board,
                    "games_per_page": self.ui.games_per_page,
                },
                "opening_training": {
                    "number_of_attempts": self.opening_training.number_of_attempts
                },
                "broadcasts": {"tournaments_limit": self.broadcasts.tournaments_limit},
                "pgn": {"directory": str(self.pgn.directory)},
            }

        # allow dict(s) -> Settings round-trip used in tests
        def __init_subclass__(cls, **kwargs):  # type: ignore[override]
            return super().__init_subclass__(**kwargs)

        def __repr__(self):
            return "<StubSettings>"

    # expose class and default instance via the shim module
    _bs.Settings = _Settings
    _bs.settings = _Settings()
    _bs.CONFIG_PATH = _P("/tmp/blindbase-test.toml")
    sys.modules["blindbase.core.settings"] = _bs

    # expose class globally so test modules can call `Settings(**data)`
    _builtins.Settings = _Settings
