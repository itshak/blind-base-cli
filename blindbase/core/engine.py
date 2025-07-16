"""Simple Stockfish engine manager used across the CLI.

We keep a single engine process (lazy-initialised) so multiple panels can share
it.  A context manager wrapper ensures it is gracefully closed on interpreter
exit.

If the *STOCKFISH_EXECUTABLE* env var is set we use it; otherwise we fall back
on whatever ``python-chess`` can find on PATH.
"""
from __future__ import annotations

import atexit
import os
from pathlib import Path
from threading import Lock
from typing import Optional

import chess
import chess.engine

from chess.engine import Mate, Cp

__all__ = ["Engine", "EngineError", "score_to_str"]


class EngineError(RuntimeError):
    pass


class _SingletonEngine:
    _lock = Lock()
    _engine: Optional[chess.engine.SimpleEngine] = None

    @classmethod
    def get(cls) -> chess.engine.SimpleEngine:
        with cls._lock:
            if cls._engine is None:
                exe = os.getenv("STOCKFISH_EXECUTABLE") or cls._detect_engine_path()
                try:
                    cls._engine = chess.engine.SimpleEngine.popen_uci(str(exe))
                except FileNotFoundError as exc:
                    raise EngineError(
                        f"Stockfish executable not found at '{exe}'. Set STOCKFISH_EXECUTABLE env var."
                    ) from exc
                atexit.register(cls.close)
            return cls._engine

    @staticmethod
    def _detect_engine_path() -> str:
        """Return best-guess Stockfish executable path for current platform."""
        import sys
        # If running from a PyInstaller bundle, engine binaries are unpacked to
        # the temporary _MEIPASS directory under an "engine" subfolder.
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        eng_dir = base_path / "engine"
        if not eng_dir.exists():
            return "stockfish"  # fallback to PATH
        import platform
        system = platform.system()
        if system == "Darwin":
            arch = platform.machine().lower()
            mac_dir = eng_dir / "mac"
            if arch in {"arm64", "aarch64"} and (mac_dir / "stockfish").exists():
                return str(mac_dir / "stockfish")
            elif (mac_dir / "stockfish_x86").exists():
                return str(mac_dir / "stockfish_x86")
        elif system == "Windows":
            win_file = eng_dir / "win" / "stockfish.exe"
            if win_file.exists():
                return str(win_file)
        # else linux or not found
        return "stockfish"

    @classmethod
    def close(cls) -> None:
        with cls._lock:
            if cls._engine is not None:
                try:
                    cls._engine.quit()
                except Exception:
                    pass
                cls._engine = None


def score_to_str(score: chess.engine.Score) -> str:
    if isinstance(score, Mate):
        return f"M{score.pov(chess.WHITE).mate()}"  # mate in N
    cp = score.pov(chess.WHITE).score()
    if cp is None:
        return str(score)
    sign = "+" if cp > 0 else ""  # SHOW + for positive
    return f"{sign}{cp/100:.2f}"


class Engine:
    """Facade used by callers."""

    @staticmethod
    def get() -> chess.engine.SimpleEngine:
        """Returns the singleton engine instance."""
        return _SingletonEngine.get()

    @staticmethod
    def evaluate(board: chess.Board, depth: int = 15) -> chess.engine.Score:
        eng = _SingletonEngine.get()
        info = eng.analyse(board, chess.engine.Limit(depth=depth))
        if isinstance(info, list):
            info = info[0]
        return info["score"]

    @staticmethod
    def best_line(board: chess.Board, depth: int = 15):
        eng = _SingletonEngine.get()
        info = eng.analyse(board, chess.engine.Limit(depth=depth), multipv=1)
        if isinstance(info, list):
            info = info[0]
        pv = info.get("pv", [])
        return pv, info["score"]
