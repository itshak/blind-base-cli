"""Re-export GameNavigator in the core namespace for refactored modules."""
from __future__ import annotations

from blindbase.navigator import GameNavigator  # noqa: F401

__all__ = ["GameNavigator"]
