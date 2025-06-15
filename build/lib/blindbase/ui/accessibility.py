import os


def screen_reader_mode() -> bool:
    """Return True if screen-reader mode is enabled.

    Currently enabled by environment variable BLINDBASE_SCREEN_READER=1.
    Later we could add a settings toggle.
    """
    return os.getenv("BLINDBASE_SCREEN_READER", "0") == "1" 