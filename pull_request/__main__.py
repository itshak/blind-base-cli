"""Package entry-point that launches the new main menu or forwards arguments.

This thin wrapper simply delegates to ``blindbase.menu.main`` so that users can
run either::

    python -m blindbase [options]
    blindbase [options]

"""
from __future__ import annotations

import sys
from blindbase.menu import main as _main

if __name__ == "__main__":  # pragma: no cover
    _main(sys.argv[1:])
