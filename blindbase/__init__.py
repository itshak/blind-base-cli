import os
# Ensure the bundled executable uses pydantic's pure-python fallback when the compiled
# shared library `pydantic_core` is missing (e.g., in PyInstaller one-file builds).
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")

__version__ = "0.10.4"

# Legacy imports (SettingsManager, GameManager, BroadcastManager, GameNavigator)
# were removed in v0.10.4 together with the monolithic CLI.  Their functionality
# now resides in `blindbase.core.*` and the Typer CLI commands.

from .analysis import (
    get_analysis_block_height,
    clear_analysis_block_dynamic,
    print_analysis_refined,
    analysis_thread_refined,
)  # noqa: F401

from .app import app as typer_app  # noqa: F401 