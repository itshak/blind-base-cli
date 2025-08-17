"""BlindBase package init.

We *do not* unconditionally force Pydantic to use its
pure-python fallback here.  The compiled Rust extension
`pydantic_core` is desirable on native platforms (e.g. arm64 macOS)
for performance and compatibility.

A dedicated PyInstaller runtime-hook (`packaging/pyi_rth_pydantic_purepython.py`)
sets `PYDANTIC_PUREPYTHON=1` and injects a stub module **only inside the
frozen executable** when the wheel for the current architecture is absent.
"""

import os

__version__ = "0.11.16"

# Legacy imports (SettingsManager, GameManager, BroadcastManager, GameNavigator)
# were removed in v0.10.21 together with the monolithic CLI.  Their functionality
# now resides in `blindbase.core.*` and the Typer CLI commands.

from .analysis import (
    get_analysis_block_height,
    clear_analysis_block_dynamic,
    print_analysis_refined,
    analysis_thread_refined,
)  # noqa: F401

from .app import app as typer_app  # noqa: F401 