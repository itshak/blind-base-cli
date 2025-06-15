import os
import sys

UI_SCREEN_BUFFER_HEIGHT = 35  # preserved for compatibility


def clear_screen_and_prepare_for_new_content(is_first_draw: bool = False):
    """Clear the terminal, respecting platform differences.

    Copied verbatim from the original monolith so other modules can import it
    without creating circular dependencies.
    """
    if is_first_draw:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")
        return

    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")
    sys.stdout.flush() 