"""Minimal UI base abstractions used during the refactor.

This deliberately keeps dependencies light.  Later phases may extend the
feature-set (navigation loop, footer, etc.) but for now we only need a common
`View` protocol that can *show()* itself.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from rich.console import Console, RenderableType

_console: Console | None = None

def _get_console() -> Console:
    global _console
    if _console is None:
        # We disable soft_wrap so board rows align nicely.
        _console = Console(highlight=False, soft_wrap=False)
    return _console


class View(ABC):
    """Renderable part of the UI.

    Sub-classes override :meth:`body` – the main content.  ``show()`` clears the
    screen and prints header/body/footer.
    """

    def show(self) -> None:
        console = _get_console()
        console.clear()
        console.print(self.header())
        console.print()  # blank line
        console.print(self.body())
        console.print()  # blank line
        console.print(self.footer())

    # ---------------------------------------------------------------------
    # Hooks that sub-classes can override
    # ---------------------------------------------------------------------

    def header(self) -> RenderableType:  # noqa: D401 – simple description
        return "BlindBase"

    def footer(self) -> RenderableType:  # noqa: D401 – simple description
        return ""

    @abstractmethod
    def body(self) -> RenderableType:  # noqa: D401 – simple description
        """Return Rich renderable for main content."""
        raise NotImplementedError
