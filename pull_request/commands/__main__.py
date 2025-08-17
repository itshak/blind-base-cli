"""PEP 338 support: ``python -m blindbase.commands``.

This thin wrapper simply forwards execution to the ``main`` function defined
in :pymod:`blindbase.commands` so that both forms work:

    $ python -m blindbase.commands ...
    $ python -m blindbase.commands pgn show my.pgn

The latter currently raises an error because the *pgn* sub-command has not yet
been implemented – that will be added in Phase 3.
"""
from __future__ import annotations

from blindbase.commands import main

if __name__ == "__main__":  # pragma: no cover
    main()
