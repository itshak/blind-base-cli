__version__ = "0.10.0"

# Legacy imports (SettingsManager, GameManager, BroadcastManager, GameNavigator)
# were removed in v0.10.0 together with the monolithic CLI.  Their functionality
# now resides in `blindbase.core.*` and the Typer CLI commands.

from .analysis import (
    get_analysis_block_height,
    clear_analysis_block_dynamic,
    print_analysis_refined,
    analysis_thread_refined,
)  # noqa: F401

from .app import app as typer_app  # noqa: F401 