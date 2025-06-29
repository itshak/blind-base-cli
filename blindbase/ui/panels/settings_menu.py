"""Interactive settings menu panel.

The panel is intentionally simple: it prints all leaf settings keys with their
current values, numbered.  The user can:

1. Press the number to change that setting – they will be prompted for a new
   value which is parsed into the existing value's type.
2. Press "s" to save & quit, or "q" to quit without saving.

It is designed to run inside the terminal, hiding the previous screen (Game
View) temporarily.  Upon return the caller can re-render the board.
"""
from __future__ import annotations

from typing import Any, List, Tuple

from blindbase.core.settings import settings
from blindbase.ui.utils import clear_screen_and_prepare_for_new_content
from rich.console import Console
from rich.table import Table
from blindbase.ui.utils import show_help_panel
from rich.panel import Panel
from rich.text import Text
from blindbase.sounds_util import play_sound

console = Console()

# Descriptions for user-friendly wording
_DESCRIPTIONS = {
    # explicit friendly names; fallback generated automatically

    "ui.move_notation": "Move notation style",
    "engine.lines": "Number of engine lines to show",
    "opening_tree.lichess_moves": "Moves to fetch from Lichess",
    "ui.theme": "Colour theme",
    "ui.board_theme": "Board theme",
}

def _pretty_name(key: str) -> str:
    """Convert dotted_key to user-friendly words."""
    parts = key.split(".")
    words = []
    for p in parts:
        words.extend(p.split("_"))
    return " ".join(w.capitalize() for w in words)

# Enumerated option lists
_ENUM_OPTIONS: dict[str, list[Any]] = {
    "ui.move_notation": ["san", "uci", "anna", "nato", "literate"],
    "ui.board_theme": ["default", "high_contrast_light", "high_contrast_dark", "colorblind_red_green"],
}


def _collect_leaf_settings() -> List[Tuple[str, Any]]:
    """Return a list of (dotted_key, value) for all leaves in *settings*."""
    out: list[tuple[str, Any]] = []

    def _recurse(prefix: str, obj: Any):
        if hasattr(obj, "model_dump"):
            data = obj.model_dump()
        elif isinstance(obj, dict):
            data = obj
        else:
            out.append((prefix.rstrip("."), obj))
            return
        for k, v in data.items():
            _recurse(f"{prefix}{k}.", v)

    _recurse("", settings)
    out.sort()
    return out


def _set_setting(dotted_key: str, new_value_str: str) -> bool:
    """Set *dotted_key* inside global settings to *new_value_str* parsed."""
    parts = dotted_key.split(".")
    obj = settings
    for p in parts[:-1]:
        obj = getattr(obj, p)
    leaf_name = parts[-1]
    current = getattr(obj, leaf_name)
    # try to coerce type
    try:
        if isinstance(current, bool):
            new_val = new_value_str.lower() in {"1", "true", "yes", "y"}
        elif isinstance(current, int):
            new_val = int(new_value_str)
        elif isinstance(current, float):
            new_val = float(new_value_str)
        else:
            new_val = type(current)(new_value_str)  # type: ignore[call-arg]
    except Exception:
        print("Invalid value type; change cancelled.")
        input("Press Enter to continue…")
        return False
    setattr(obj, leaf_name, new_val)
    return True


def _collect_categories() -> list[str]:
    return [fld for fld in settings.model_dump().keys()]

def run_settings_menu() -> None:
    play_sound("notify.mp3")
    changed = False
    current_category: str | None = None
    while True:
        clear_screen_and_prepare_for_new_content()
        if current_category is None:
            # Top-level category selection
            clear_screen_and_prepare_for_new_content()
            cats = _collect_categories()
            tbl = Table(show_header=True, header_style="bold magenta")
            tbl.add_column("#", justify="right", style="cyan")
            tbl.add_column("Category")
            for idx, cat in enumerate(cats, 1):
                tbl.add_row(str(idx), _pretty_name(cat))
            console.print(Panel(tbl, title="Settings Categories", border_style="green"))
            choice = input("Command (h for help): ").strip().lower()
            if choice == "q":
                play_sound("click.mp3")
                if changed and input("Save changes before quitting? (Y/n): ").strip().lower() in {"", "y", "yes"}:
                    settings.save()
                break
            if choice == "h":
                show_help_panel(console, "Settings – Help", [
                    ("<number>", "open that category"),
                    ("q", "quit (prompt to save)"),
                    ("h", "help"),
                ])
                input("Press Enter…")
                continue
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(cats):
                    current_category = cats[idx]
                    play_sound("click.mp3")
                else:
                    play_sound("decline.mp3")
                continue
            play_sound("decline.mp3")
            continue
        # ------------ leaf submenu -            clear_screen_and_prepare_for_new_content()
        leafs = [ (k, v) for k, v in _collect_leaf_settings() if k.startswith(f"{current_category}.") ]
        # Build rich table grouped by section
        tbl = Table(show_header=True, header_style="bold magenta")
        tbl.add_column("#", justify="right", style="cyan")
        tbl.add_column("Setting")
        tbl.add_column("Value", style="yellow")
        for idx, (key, val) in enumerate(leafs, 1):
            short_key = key[len(current_category)+1:]
            desc = _DESCRIPTIONS.get(key) or _pretty_name(short_key)
            tbl.add_row(str(idx), desc, str(val))
        console.print(Panel(tbl, title=f"{_pretty_name(current_category)} Settings", border_style="green"))
        choice = input("Command (h for help): ").strip().lower()
        if choice == "b":
            play_sound("click.mp3")
            current_category = None
            continue
        if choice == "q":
            play_sound("click.mp3")
            if changed:
                if input("Save changes before quitting? (Y/n): ").strip().lower() in {"", "y", "yes"}:
                    settings.save()
            break
        if choice == "h":
            show_help_panel(console, "Settings – Help", [
                ("<number>", "edit that setting"),
                ("s", "save changes & stay"),
                ("b", "back to categories"),
                ("q", "quit (prompt to save if changes)"),
                ("h", "show this help"),
            ])
            input("Press Enter to continue…")
            continue
        if choice == "s":
            play_sound("click.mp3")
            if changed:
                settings.save()
                print("Settings saved.")
                input("Press Enter to continue…")
            break
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(leafs):
                play_sound("click.mp3")
                key, val = leafs[idx]
                full_key = key
                short_key = key[len(current_category)+1:]
                label = _DESCRIPTIONS.get(full_key) or _pretty_name(short_key)
                if full_key in _ENUM_OPTIONS:
                    opts = _ENUM_OPTIONS[full_key]
                    console.print(Text(f"Choose {label.lower()}:", style="bold"))
                    console.print(Panel("\n".join(f"{i+1}. {opt}" for i, opt in enumerate(opts)), title="Options", border_style="blue"))
                    sel = input("Select number: ").strip()
                    if sel.isdigit() and 1 <= int(sel) <= len(opts):
                        if _set_setting(full_key, opts[int(sel)-1]):
                            changed = True
                    else:
                        input("Invalid option. Press Enter…")
                        play_sound("decline.mp3")
                elif isinstance(val, bool):
                    console.print(Text(f"Choose {label.lower()}:", style="bold"))
                    console.print(Panel("1. Yes\n2. No", title="Options", border_style="blue"))
                    sel = input("Select number: ").strip()
                    if sel in {"1", "2"}:
                        if _set_setting(full_key, sel):
                            changed = True
                    else:
                        input("Invalid option. Press Enter…")
                        play_sound("decline.mp3")
                else:
                    new_val_str = input(f"Enter new value for {label} (current {val}): ").strip()
                    if new_val_str:
                        if _set_setting(full_key, new_val_str):
                            changed = True
            else:
                input("Invalid number. Press Enter…")
                play_sound("decline.mp3")

        else:
            input("Unknown command. Press Enter…")
            play_sound("decline.mp3")
